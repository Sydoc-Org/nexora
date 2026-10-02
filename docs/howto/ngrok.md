# ngrok setup (SYAPP01) — one endpoint per host

One ngrok agent (Windows service `ngrok`) on SYAPP01 fronts every hosted
environment (#338): PROD, staging and the dev hosts. It reads
`D:\sydoc\nexora\ngrok.yaml`, which is **not** in git (it holds the authtoken)
and is in `deploy-env.yml`'s robocopy `/XF` list, so deploys never touch it. Deploys also never stop the service any more: a stopped
app pool answers 503 while the mirror runs, which is enough.

| host | local upstream | folder | `ENVIRONMENT` | deployed by |
|---|---|---|---|---|
| `nexora.sydoc.ch` | `http://localhost:80` (IIS Default Web Site, `DefaultAppPool`) | `D:\sydoc\nexora` | `PROD` | push of a `v*` tag |
| `staging-nexora.sydoc.ch` | `http://127.0.0.1:8082` (site `nexora-staging`) | `D:\sydoc\nexora-staging` | `STAGING` | merge to `main` + 01:30 nightly, or Run workflow on `main` |
| `stop-taking-my-gitrunner-nexora.sydoc.ch` | `http://127.0.0.1:8083` (site `nexora-dev-ben`) | `D:\sydoc\nexora-dev-ben` | `INT` | any other branch push by `benstreich` |
| `prod-but-not-really-nexora.sydoc.ch` | `http://127.0.0.1:8084` (site `nexora-dev-gruoss`) | `D:\sydoc\nexora-dev-gruoss` | `INT` | any other branch push by `GRuoss` |

**Dev hosts are per developer (#431).** Each pusher has their own dev host, so two
people pushing at once no longer overwrite each other. The test job's *Resolve dev
slot* step in `.github/workflows/deploy.yml` maps the GitHub login to a slot. A
pusher with no slot (a bot, an occasional contributor) gets the tests but no dev
deploy, and so does a mapped developer whose folder does not exist yet (with a
warning on the run). The shared `dev-nexora.sydoc.ch` host is retired. Each
slot deploys in its own concurrency group. All dev hosts share the INT
databases, so a migration one person's branch applies is live for everyone.

## DNS (cyon)

`sydoc.ch` DNS stays at cyon. Each host is a CNAME to its own ngrok edge target
(ngrok dashboard → *Domains*; the target is per domain):

| record | CNAME target |
|---|---|
| `nexora` | `dzpsykqcwgqzfk1c.zgzyk2x2s1c7jrr8.ngrok-cname.com` |
| `staging-nexora` | `62ubvmwfstncuu83.zgzyk2x2s1c7jrr8.ngrok-cname.com` |
| `stop-taking-my-gitrunner-nexora` | *(from the ngrok dashboard once the domain is reserved, #431)* |
| `prod-but-not-really-nexora` | *(from the ngrok dashboard once the domain is reserved, #431)* |

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
  - name: nexora-dev-ben
    url: https://stop-taking-my-gitrunner-nexora.sydoc.ch
    upstream:
      url: http://127.0.0.1:8083
  - name: nexora-dev-gruoss
    url: https://prod-but-not-really-nexora.sydoc.ch
    upstream:
      url: http://127.0.0.1:8084
  - name: nexora-staging
    url: https://staging-nexora.sydoc.ch
    upstream:
      url: http://127.0.0.1:8082
```

`ops/setup-env.ps1` appends the dev/staging entries (idempotent) and restarts
the service; it assumes `endpoints:` is the last top-level key. The upstream must
be `http://127.0.0.1:<port>`, not a bare port: a bare port means `localhost`,
which Windows resolves to `::1`, and the loopback-only IIS binding then answers
`400 Bad Request - Invalid Hostname` from HTTP.sys.

## Adding a host

RDP to SYAPP01, elevated PowerShell, once per environment:

```powershell
cd D:\sydoc\tools
.\setup-env.ps1 -Name staging    -Port 8082 -Environment STAGING -Hostname staging-nexora.sydoc.ch
.\setup-env.ps1 -Name dev-ben    -Port 8083 -Environment INT -Hostname stop-taking-my-gitrunner-nexora.sydoc.ch
.\setup-env.ps1 -Name dev-gruoss -Port 8084 -Environment INT -Hostname prod-but-not-really-nexora.sydoc.ch
```

(The script ships in the repo as `ops/setup-env.ps1`; copy it to `D:\sydoc\tools`
first — `tools\` is outside the deploy mirror.) Then push the env file from a
dev box: `python scripts/env-sync.py --push INT.env` / `--push STAGING.env`
(`--push INT.env` writes every `nexora-dev-*` folder it finds).

**Adding a developer's dev host** (#431), in this order:

1. ngrok dashboard → *Domains* → reserve the developer's hostname (any name,
   it need not match the slot); add its CNAME at cyon (table above).
2. On SYAPP01: `.\setup-env.ps1 -Name dev-<who> -Port <next free, 8085+> -Environment INT -Hostname <their-host>.sydoc.ch`.
3. From a dev box: `python scripts/env-sync.py --push INT.env`.
4. Add `'<github-login>' = 'dev-<who>'` to *Resolve dev slot* in `deploy.yml`,
   and a row to the tables here and in `docs/howto/iis.md`.

Until step 4 merges, that developer's pushes run the tests but deploy nowhere.

**Removing a host** (as done for the shared `dev-nexora`, #431): drop its slot
from `deploy.yml` first and merge, then on SYAPP01 remove the IIS site and app
pool (`Remove-Website`, `Remove-WebAppPool`), its `ngrok.yaml` entry
(`Restart-Service ngrok`) and folder; finally release the domain in the ngrok
dashboard and delete the CNAME at cyon.

## Service commands

```powershell
cd /d "D:\sydoc\tools\ngrok"
ngrok start --config="D:\sydoc\nexora\ngrok.yaml" --all      # run in the foreground
ngrok service install --config="D:\sydoc\nexora\ngrok.yaml"  # once, elevated
ngrok service start
Restart-Service ngrok                                        # after editing ngrok.yaml
```

Cloudflare Tunnel was evaluated and parked — see `docs/howto/cloudflare-tunnel.md`.
