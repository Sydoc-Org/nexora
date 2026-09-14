# Handoff — dev/staging environments shipped, v3.2.5 is the first tag-deployed PROD release

**Date:** 2026-09-14 · **Branch:** `docs/338-final-handoff` (this file only; PR to `main`) ·
everything else is on `main` · #338 **closed** · worktree and merged branches removed.

**Prior handoff:** [`2026-09-14-dev-staging-envs-execution-complete.md`](2026-09-14-dev-staging-envs-execution-complete.md)
(state before the merges — superseded by this one).

## TL;DR

| host | state | footer at handoff |
|---|---|---|
| `https://dev-nexora.sydoc.ch/` | live, redeploys on any non-`main` branch push | last pushed branch |
| `https://staging-nexora.sydoc.ch/nexora/` | live, prod-shaped (CSP, HSTS, `/nexora`, `/dev/*` 404), redeploys on merge to `main` and nightly 01:30 | `8a33005 (main)` |
| `https://nexora.sydoc.ch/nexora/` | live, **deployed by tag `v3.2.5`** — `main` no longer touches PROD | `nexora v3.2.5 · 8a33005, 2026-09-14` |

- PR #344 (`e568bc50`) — the environments; PR #345 (`8a330059`) — release chore 3.2.5 + What's New card; tag `v3.2.5` on `8a330059`.
- Two live bugs found and fixed on the dev host during rollout: `/dev/login` reachable publicly (IIS is waitress's socket peer → guard now also refuses `X-Forwarded-For` / non-loopback `Host`, `3e1fdef6`), and `API_PREFIX` decided by `location.href.includes('nexora')` (hostname matched → every API call 404; now first path segment, lint-tested, `5d868b87`).
- Staging DBs `nexora_STAGING` / `Generali_STAGING` on PRDSQL01, rebuilt nightly 01:00 by SQL Agent job `nexora - staging refresh` (`ops/staging-refresh.sql`), then the 01:30 GitHub schedule redeploys `main` to staging and re-applies pending migrations.

## Next steps

1. **Tomorrow morning:** `sys.databases` shows fresh `create_date` on both `_STAGING` DBs; Actions shows a green scheduled Deploy run at 01:30 with only `deploy-staging` executed and the 03:00 e2e run untouched.
2. Owner check of the What's New card on PROD (badge lights, text reads right) — copy is in `nx_lib/whats_new.py` under `3.2.5`.
3. Releases from now on: `CONTRIBUTING.md` → Releases. Merge = staging, tag = PROD. Tag promptly after release-worthy merges.
4. Memory drift to fix when convenient: notes claiming INT DBs are `NexoraDB_INT` — real names are `nexora` / `Generali` on `INTSQL01`.

## Gotchas learned this rollout

- ngrok upstream must be `http://127.0.0.1:<port>`; a bare port means `localhost` → `::1` → HTTP.sys 400 against the loopback-only IIS binding.
- `setup-env.ps1` needs Windows PowerShell 5.1 for the `IIS:` drive; it relaunches itself from pwsh.
- The pre-push hook rejects `plan/*` branch names; gitlint caps subjects at 72 chars.
- The runner pins ruff 0.7.4; a locally "formatted" file can still fail the format check.
- Single self-hosted runner: a tag run queues behind a `main` run (≈ 20 min for both).
- `env-sync.py` reports 12 defaulted keys absent on PROD — pre-existing, owner says not used, leave it.

## How to verify

```powershell
curl -sI https://nexora.sydoc.ch/nexora/login | Select-String '^HTTP'                  # 200
curl -s  https://nexora.sydoc.ch/nexora/login | Select-String 'nexora v3\.2\.5'         # footer
curl -sI https://staging-nexora.sydoc.ch/nexora/login | Select-String 'content-security-policy'
curl -sI https://dev-nexora.sydoc.ch/dev/login/x | Select-String '^HTTP'               # 404
gh run list --limit 5                                                                   # tag run: deploy-prod success
```

## Resuming in a fresh session

Nothing is in flight. `/reset-session docs/superpowers/handoffs/2026-09-14-dev-staging-envs-shipped.md`
if you want the context; otherwise start clean. Decision record: issue #338.
