> **Superseded:** shipped the same day — read [`2026-09-14-dev-staging-envs-shipped.md`](2026-09-14-dev-staging-envs-shipped.md) instead.

# Handoff — dev/staging environments (#338) built, dev host live; PR + merge + first tag pending

**Date:** 2026-09-14 · **Branch:** `feat/338-dev-staging-envs` (renamed from `plan/dev-staging-envs-ngrok`
for the pre-push hook) in worktree `.claude/worktrees/plan-dev-staging-envs-ngrok` (folder name kept) ·
**pushed to origin, 14 commits ahead of `main` @ `aae7c492`, no PR yet** · owner authorised push this session ·
execution complete, **worktree kept** until merged.

**Prior handoff:** [`2026-09-14-dev-staging-envs-ngrok-plan.md`](2026-09-14-dev-staging-envs-ngrok-plan.md)
(the plan; consumed by this session).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `eece0f2e` `3f0e3d59` `fd86f338` | plan, plan handoff, ngrok CNAME targets |
| `6cc23d30` | `feat(config)`: `IS_PROD` true for `STAGING` |
| `aad6915a` | `feat(env)`: examples + `DB_GENERALI`, `env-sync.py` per-folder mapping, `scripts/make-staging-env.py` |
| `6b72e246` `a22763e5` `7efd8154` `2ba6d2cf` | `ops/setup-env.ps1` (+ pwsh relaunch, path fix, `127.0.0.1` upstream) |
| `ae7ead01` | `ci`: reusable `.github/workflows/deploy-env.yml` |
| `58cf37db` | `ci`: `deploy.yml` → branch→dev, main→staging, `v*` tag→prod; `pull_request` trigger removed |
| `3cbe154f` | `test`: prune tests follow the moved steps; prod-only task registration pinned |
| `ed461e73` | `ops/staging-refresh.sql` — SQL Agent job, installed and run on PRDSQL01 |
| `08b8c525` | docs + changelog |
| `3e1fdef6` | **`fix(auth)`: `/dev/*` refuses proxied / non-loopback-host requests** (security, see below) |

## TL;DR

- **`https://dev-nexora.sydoc.ch` is live** on the last pushed branch (footer `3e1fdef (feat/338-dev-staging-envs)`),
  deployed twice by the new pipeline (test → `deploy-dev`, prod/staging skipped as intended).
- **Staging is fully prepared but has never deployed**: it deploys on the first merge to `main`.
  `nexora_STAGING` / `Generali_STAGING` exist on PRDSQL01 (job `nexora - staging refresh`, 01:00 daily, 17 s),
  `STAGING.env` is on SYAPP01, the IIS site/pool/ngrok endpoint exist, `https://staging-nexora.sydoc.ch` answers
  IIS 403.14 (empty folder) — correct until the first deploy.
- **PROD contract changed on this branch**: after merge, `main` deploys staging and only a `v*` tag deploys PROD.
- **Security incident, closed:** the first dev deploy exposed `/dev/login/<user>` publicly (passwordless session).
  Cause: IIS is waitress's socket peer, so `remote_addr` was `127.0.0.1` for every request and the old guard passed.
  Mitigated within seconds by moving the dev `web.config` aside; fixed in `3e1fdef6` (guard also refuses
  `X-Forwarded-For` and non-loopback `Host`); redeployed and verified `404`. Window ≈ 15 minutes, hostname
  unpublished, no sign of use — `D:\sydoc\nexora-dev\var\logs\user\` CSV would show any other caller.

## What shipped

| Area | Files |
|---|---|
| Config | `nx_lib/config.py` (`IS_PROD`), `tests/unit/test_is_prod_flag.py` |
| Env plumbing | `env/{INT,PROD,STAGING}.env.example`, `scripts/env-sync.py` (`MANAGED` dict + `remote_path`), `scripts/make-staging-env.py`, tests |
| CI | `.github/workflows/deploy-env.yml` (new), `.github/workflows/deploy.yml` (triggers + 3 callers), `tests/unit/test_prune_*.py` |
| Server | `ops/setup-env.ps1` (also at `D:\sydoc\tools\`), `ops/staging-refresh.sql` (installed on PRDSQL01) |
| Auth | `nx_lib/views/auth.py::_dev_route_forbidden`, `tests/integration/test_auth_routes.py` (+2) |
| Docs | `docs/howto/ngrok.md` (rewritten), `cloudflare-tunnel.md` (parked), `iis.md`, `db-migrations.md`, `outage-monitor.md`, `CONTRIBUTING.md`, `README.md`, `CLAUDE.md`, `CHANGELOG.md` |

Live state changed outside git: SYAPP01 `D:\sydoc\nexora-dev`, `D:\sydoc\nexora-staging` (+ pools, sites,
Defender exclusions, env files), `D:\sydoc\nexora\ngrok.yaml` (+2 endpoints, upstream `http://127.0.0.1:<port>`),
PRDSQL01 two databases + one Agent job, cyon two CNAMEs, ngrok two custom domains.

## Next steps (in order)

1. **Owner review, then PR** `feat/338-dev-staging-envs` → `main` (not opened this session; owner said "commit and push").
   Merge triggers the first **staging** deploy — watch it; expected green.
2. Verify staging: `https://staging-nexora.sydoc.ch/nexora/login` → 200 with a `content-security-policy` header,
   footer `<sha> (main)`, `/dev/login/...` → 404. Log in against the `_STAGING` data.
3. **Tag a release promptly** (`CONTRIBUTING.md` → Releases): until a `v*` tag is pushed, PROD stays on the
   pre-merge build. The tag run should show `deploy-prod: success` and the PROD stamp change.
4. Next morning: the 01:00 job + 01:30 schedule → `sys.databases` shows fresh `create_date` on both `_STAGING`
   DBs and a green scheduled Deploy run with only `deploy-staging` executed.
5. Close #338 with the merge SHA. Remove the worktree + branch after merge (`/clean`).

## Gotchas & notes

- **ngrok upstream must be `http://127.0.0.1:<port>`**, not a bare port (→ `localhost` → `::1` → HTTP.sys 400
  "Invalid Hostname" against the loopback-only IIS binding). Documented in `ngrok.md`; fixed live.
- `setup-env.ps1` needs Windows PowerShell 5.1 for the `IIS:` drive; it relaunches itself from pwsh.
- The pre-push hook rejects `plan/*` branches — that is why the branch was renamed.
- gitlint: subjects ≤ 72 chars bit three times this session.
- `deploy.yml` no longer has a `pull_request` trigger: PR checks come from the push run on the head branch.
- The `Switch user` menu is visible on dev (INT) but its `/dev/*` calls now 404 remotely — cosmetic.
- `STAGING.env` was derived from `PROD.env` (`make-staging-env.py`): `OUTAGE_SITE_URL` etc. still point at
  prod; harmless because staging registers no scheduled tasks.
- `env-sync.py` report shows pre-existing PROD drift (12 keys with defaults absent on the server) — not #338.
- Memory/plan text claiming INT DBs are `NexoraDB_INT` is wrong: INT uses `nexora` / `Generali` on `INTSQL01`.

## Untracked / left for owner

- Worktree `env/INT.env`, `env/TEST.env`, `env/PROD.env`, `env/STAGING.env` (gitignored, copied in this session).
- Scratch generators in the session scratchpad only. Nothing untracked in the tree.

## How to verify

```powershell
cd C:\dev\nexora\.claude\worktrees\plan-dev-staging-envs-ngrok
git log --oneline main..HEAD                          # 14 commits, HEAD 3e1fdef6 (+ this handoff)
gh run list --branch feat/338-dev-staging-envs        # two green Deploy runs (deploy-dev)
curl -sI https://dev-nexora.sydoc.ch/login | Select-String '^HTTP'          # 200
curl -sI https://dev-nexora.sydoc.ch/dev/login/x | Select-String '^HTTP'    # 404
$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"
$env:ENVIRONMENT = 'TEST'; python -m pytest tests --ignore=tests/e2e -q -p no:cacheprovider   # 2631+ passed
python scripts/db-migrate.py --env STAGING --dry-run  # up-to-date
```

## Resuming in a fresh session

`/reset-session docs/superpowers/handoffs/2026-09-14-dev-staging-envs-execution-complete.md` (two handoffs share
this date; name the file). Start at "Next steps" step 1. Plan: `docs/superpowers/plans/2026-09-14-dev-staging-envs-ngrok.md`.
