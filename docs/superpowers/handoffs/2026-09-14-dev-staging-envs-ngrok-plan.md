# Handoff — dev/staging environments via ngrok endpoints (#338): plan written, not yet executed

**Date:** 2026-09-14 · **Branch:** `plan/dev-staging-envs-ngrok` in worktree
`.claude/worktrees/plan-dev-staging-envs-ngrok` (cut from `main` @ `aae7c492`; the main checkout
`C:\dev\nexora` sits on `main` with peers' uncommitted files — never touch it) ·
**2 commits ahead of `main`, nothing pushed** · commit-only (remote session) ·
plan complete, **worktree kept open** for `/execute-plan`.

**Prior handoff:** [`2026-09-08-reporting-contribution-analysis-execution-complete.md`](2026-09-08-reporting-contribution-analysis-execution-complete.md)
(unrelated feature; this is a fresh thread).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `eece0f2e` | `docs(plans)`: `docs/superpowers/plans/2026-09-14-dev-staging-envs-ngrok.md` |
| (this) | `docs(handoff)`: this file |

## TL;DR

- **Issue #338** (rewritten three times this session) is the record of the decisions: hosts
  `dev-nexora.sydoc.ch` (any branch push, port 8081, `ENVIRONMENT=INT`, INT databases) and
  `staging-nexora.sydoc.ch` (`main`, port 8082, `ENVIRONMENT=STAGING`, nightly PROD-copy databases
  `nexora_STAGING` + `Generali_STAGING` on PRDSQL01), prod moves to **`v*` tag push**.
- **Cloudflare is out.** A `nexora.sydoc.ch` sub-zone is Enterprise-only (verified on
  developers.cloudflare.com), and the owner rejects moving the whole `sydoc.ch` zone (company
  mail / other cyon services). Extra ngrok endpoints on the existing agent instead;
  cost ≈ $0.01 per active hour per custom domain on the owner's $20 pay-as-you-go plan.
- **Plan:** 8 tasks / 4 phases, every anchor verified. Resume at
  `docs/superpowers/plans/2026-09-14-dev-staging-envs-ngrok.md`, Task 1.
- Nothing is built yet. No server, DNS or database state was changed this session
  (PRDSQL01 was only queried read-only).

## What shipped

| File | Commit | Notes |
|---|---|---|
| `docs/superpowers/plans/2026-09-14-dev-staging-envs-ngrok.md` | `eece0f2e` | Decisions D1–D12, Owner actions, Tasks 1–8, verification, gotchas |
| GitHub issue #338 | — | Title + body rewritten to the ngrok design (not in git) |

## Next steps (in order)

1. **Owner (before anything is pushed):** copy `env/INT.env`, `env/TEST.env`, `env/PROD.env` into
   the worktree's `env/` (deny rule blocks Claude). Add `dev-nexora.sydoc.ch` and
   `staging-nexora.sydoc.ch` under Domains in the ngrok dashboard and create the two CNAMEs at cyon;
   targets already received and recorded in the plan's Owner actions (dev `3vvfskuc7isen9djp…`, staging `62ubvmwfstncuu83…`).
2. `/execute-plan` on the plan (or `superpowers:subagent-driven-development` task by task) inside
   the worktree. Cut `feat/338-dev-staging-envs` from the plan branch if you prefer the
   `<type>/<issue>-<slug>` naming.
3. After Task 6 produces `ops/setup-env.ps1`: **owner runs it twice over RDP on SYAPP01**
   (commands in the script synopsis) **before the branch is first pushed** — the first push
   deploys dev and its preflight requires `D:\sydoc\nexora-dev` to exist.
4. Task 7 creates the two `_STAGING` databases on PRDSQL01 and installs the 01:00 SQL Agent job —
   a real change on the production SQL server, authorised by the owner in this session
   ("You handle both restore and job"). Then `env-sync.py --push STAGING.env` / `--push INT.env`.
5. Merge → staging deploys. **Push a `v*` tag promptly afterwards: PROD no longer moves on merge.**

## Gotchas & notes

- **Real DB names differ from memory notes.** PROD app DBs are `nexora` (logical files
  `sydocportal`/`sydocportal_log`) and `Generali`; INT uses the same names on `INTSQL01`. Memory
  files claiming `NexoraDB_INT` are wrong — fix them when this lands.
- `env/STAGING.env.example` still names `NexoraDB_STAGING`, `sydoc_stat_STAGING`, `OctoDB_STAGING`
  (never existed); `DB_GENERALI` is missing from INT/PROD/STAGING examples. Task 2 fixes both.
- `ngrok.yaml` (`D:\sydoc\nexora\ngrok.yaml`, untracked, `/XF`-excluded so it survives `/MIR`)
  holds the authtoken — never print it. Its `endpoints:` list is the last top-level key; the setup
  script appends to it.
- Deploys currently stop/start the `ngrok` service; the plan removes that (shared agent, three
  sites). `tests/unit/test_prune_*.py` read `deploy.yml` text and must follow the moved steps into
  `deploy-env.yml` (Task 5).
- `IS_PROD` becomes true for `STAGING` (D1) — one line in `nx_lib/config.py`; gates CSP, `/nexora`
  prefix, filesystem sessions, `/dev/*` lockout, admin restart endpoint, Switch-user UI.
- No WinRM to SYAPP01 (`docs/howto/winrm-prod-access.md`); SMB `\\syapp01\d$` is writable.
- PRDSQL01 facts (2026-09-14): SQL 2022 Standard, Agent running, app login is sysadmin, ~700 GB
  free on `D:`, no `*STAGING*` DB yet, Ola Hallengren jobs present but unscheduled (leave alone).
- Worktree has no env files and no venv: `$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"`.
- Commit hooks: `SQL_SYNC_SKIP=1 git commit ...` worked here; never `--no-verify`.

## Untracked / left for owner

- Nothing untracked in the worktree. Main checkout carries peers' untracked `sql/GeneraliDB/**`
  files and a modified `docs/howto/winrm-prod-access.md` — not mine, not touched.
- ngrok CNAME targets, cyon CNAMEs, env file copies, RDP script run — all owner actions above.

## How to verify

```powershell
cd C:\dev\nexora\.claude\worktrees\plan-dev-staging-envs-ngrok
git log --oneline -3                     # eece0f2e plan + handoff on plan/dev-staging-envs-ngrok
git worktree list                        # worktree still registered
gh issue view 338                        # decisions match the plan's table
```

No test suite was touched this session; `pytest tests/unit` is unchanged from `main`.

## Resuming in a fresh session

`/reset-session` picks this file up (it is the only 2026-09-14 handoff). Read
`docs/superpowers/plans/2026-09-14-dev-staging-envs-ngrok.md` first — "Context an engineer needs"
and "Owner actions" — then start at Task 1 inside the worktree. Issue #338 is the decision record.
