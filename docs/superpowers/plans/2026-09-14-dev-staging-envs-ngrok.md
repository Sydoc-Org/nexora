# Dev/staging environments via ngrok endpoints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Anchor on **function names and quoted snippets**, never line numbers — re-Grep before every edit.

**Goal:** Three always-on nexora hosts on SYAPP01 — `dev-nexora.sydoc.ch` (last pushed topic branch, INT databases), `staging-nexora.sydoc.ch` (`main`, nightly PROD-copy databases) and `nexora.sydoc.ch` (last `v*` tag) — each deployed by CI, each reachable through the existing ngrok agent.

**Architecture:** The deploy job of `.github/workflows/deploy.yml` becomes a reusable workflow (`deploy-env.yml`, `on: workflow_call`) parameterised by environment name, target folder and app pool; `deploy.yml` keeps the test job and grows three thin caller jobs with the branch / `main` / tag conditions. Server-side, one PowerShell script (`ops/setup-env.ps1`, run once over RDP) creates the extra IIS sites, app pools, folders, Defender exclusions and ngrok endpoints. Staging data is a nightly `BACKUP ... WITH COPY_ONLY` + `RESTORE ... WITH REPLACE` SQL Agent job on PRDSQL01 (`ops/staging-refresh.sql`), followed by a scheduled staging redeploy that re-applies pending migrations. One line in `nx_lib/config.py` makes `STAGING` behave like `PROD` (sessions, CSP, `/nexora` prefix, dev-route lockout).

**Tech Stack:** GitHub Actions (self-hosted Windows runner, PowerShell 5.1 steps), IIS + HttpPlatformHandler + waitress, ngrok agent v3 (`endpoints:` config), SQL Server 2022 Standard T-SQL + SQL Agent, `scripts/db-migrate.py`, `scripts/env-sync.py`, pytest.

**Spec:** none (decisions recorded in GitHub issue #338 and in the table below). Issue: #338.

## Global Constraints

- Hostnames are the **hyphen** form (`dev-nexora.sydoc.ch`, `staging-nexora.sydoc.ch`); `sydoc.ch` DNS stays at cyon; no Cloudflare anywhere (subdomain zones are Enterprise-only, whole-zone move rejected — #338).
- Ports: dev **8081**, staging **8082**, bound to `127.0.0.1` only; prod stays on port 80 / `DefaultAppPool` / `D:\sydoc\nexora` untouched.
- Folders: `D:\sydoc\nexora-dev`, `D:\sydoc\nexora-staging`. App pools: `nexora-dev`, `nexora-staging`. IIS sites: same names.
- `ENVIRONMENT` values: dev = `INT`, staging = `STAGING`, prod = `PROD`. Env files live at `<folder>\env\<ENV>.env` plus the root selector `<folder>\.env` (`ENVIRONMENT=<ENV>`), exactly like prod.
- Databases: dev → the INT server (`INTSQL01`, whatever `env/INT.env` on the dev box points at today). Staging → **PRDSQL01**, `nexora_STAGING` + `Generali_STAGING` (PROD's app DBs are `nexora` and `Generali`; logical file names `sydocportal`/`sydocportal_log` and `Generali`/`Generali_log`). Octo (`RuntimeDatabase`), Statistics (`SYDOC_Statistik`) and the MS02 Postgres DBs are read-only vendor surfaces → staging uses the PROD instances.
- **Prod deploys on tag only** after this lands. `main` deploys staging. Any other branch push deploys dev (last push wins).
- The ngrok service is **never stopped** by a deploy any more (three sites share it; a stopped app pool already answers 503).
- Never `--no-verify`. If the SQL hooks block on unrelated INT drift, `SQL_SYNC_SKIP=1 git commit ...`.
- **Commit only — no push, no PR this session** unless the owner says otherwise; the first push of this branch will itself trigger a dev deploy (see Owner actions ordering).

---

## Context an engineer needs (read first)

- **Branch / worktree:** plan written on `plan/dev-staging-envs-ngrok` in worktree `.claude/worktrees/plan-dev-staging-envs-ngrok` (cut from `main` @ `aae7c492`). Execute there, or cut `feat/338-dev-staging-envs` from it. The main checkout `C:\dev\nexora` sits on `main` with peers' uncommitted files — never touch it.
- **Worktree has no secrets or venv.** `env/*.env` are gitignored and a deny rule blocks Claude from copying them — the **owner** copies `env/INT.env`, `env/TEST.env` and `env/PROD.env` into the worktree's `env/` before Task 7. `$env:PATH = "C:\dev\nexora\.venv\Scripts;$env:PATH"` before any `pytest` / `python scripts/...`.
- **No WinRM to SYAPP01** (`docs/howto/winrm-prod-access.md`): files go over `\\syapp01\d$`, commands run either over RDP (owner) or inside a workflow on the self-hosted runner. The runner service account already stops/starts `DefaultAppPool` and runs `robocopy` into `D:\sydoc\nexora`; it will need the same rights on the two new folders/pools (the setup script grants them, Task 6).
- **`IS_PROD` gates** (`nx_lib/config.py`: `IS_PROD = os.environ.get("ENVIRONMENT") == "PROD"`): filesystem sessions + secure cookies (`nx_lib/__init__.py` `if cfg.IS_PROD:` ×3 — sessions, Talisman CSP, `PrefixMiddleware(app.wsgi_app, prefix="/nexora")`), the `/dev/*` lockout in `nx_lib/views/auth.py::_dev_route_forbidden`, the restart endpoint in `nx_lib/views/admin/system.py`, and the `{% if not is_prod %}` "Switch user" UI in `templates/_header.html`. Staging must look like prod → Task 1 widens the flag. Dev keeps INT behaviour; `_dev_route_forbidden` already 404s non-loopback callers (#193), so the public dev host cannot use `/dev/login`.
- **`web.config` is tracked and PROD-hardcoded** (`<environmentVariable name="ENVIRONMENT" value="PROD" />`, `PYTHONPATH` and `stdoutLogFile` under `D:\sydoc\nexora`). `robocopy /MIR` copies it into every folder, so the reusable workflow patches the three values **after** the mirror for non-prod targets (Task 3). `tests/unit/test_iis_hosting.py` asserts the tracked file says `PROD` — unchanged.
- **`ngrok.yaml` lives at `D:\sydoc\nexora\ngrok.yaml`**, is *not* tracked, and is in the robocopy `/XF` list → it survives `/MIR`. Current content: `version: 3`, `agent: authtoken`, one entry under `endpoints:` named `nexora-app` with `url: https://nexora.sydoc.ch`, `upstream: url: 80`, and a bot-blocking `traffic_policy`. Task 6 appends two endpoints; the authtoken is a secret — never print the file.
- **Deploy-time facts** (`deploy.yml` today): root `.env` selector check (`ENVIRONMENT=PROD`), IIS preflight, LF-normalise `sql/`, `db-migrate.py --env PROD --yes` with `env/PROD.env` copied from the deploy folder into the workspace, stop pool **and** tunnel services, `robocopy /MIR` with `/XD ... /XF ...`, orphan sweeps, `nx_lib\_build.py` build stamp, start pool + tunnels, `Register scheduled tasks` (prod-only concern: Outage Monitor, Prune Sessions, Prune Request Log). Legacy root `PROD.env` fallback can go — `\\syapp01\d$\sydoc\nexora\env\PROD.env` exists.
- **Tests pinned to `deploy.yml` text:** `tests/unit/test_prune_active_sessions.py` (reads the `/XD` line and the task-registration step) and `tests/unit/test_prune_request_log.py` (`workflow = (REPO / ".github" / "workflows" / "deploy.yml").read_text(...)`). They must follow the robocopy / task steps into `deploy-env.yml` (Task 5).
- **Scheduled side effects are not in-process.** Reporting mails run from `ops/run_scheduled_reports.py` and outage alerts from `ops/outage_monitor.py`, both as Windows scheduled tasks pointed at `D:\sydoc\nexora`. Dev/staging never register tasks → no duplicate mails. Interactive mails (password reset via `nx_lib/mail.py::send_mail`) still fire from staging; acceptable, documented.
- **PRDSQL01 facts (checked 2026-09-14):** `PRDSQL01\PRDSQL01`, SQL Server 2022 Standard (backup `COMPRESSION` allowed), SQL Agent running, the app login in `env/PROD.env` is `sysadmin`, `D:` has ~700 GB free, `D:\tmp` exists (used by the external `sqlBackuper.ps1`, which uploads to Azure and deletes local files — there is **no** durable `.bak` on disk, hence our own COPY_ONLY step). Data/log paths: `D:\data\`, `D:\log\`. No `*STAGING*` database exists. Ola Hallengren jobs exist but are unscheduled — leave them alone.
- **`scripts/env-sync.py`** only knows `MANAGED = ("PROD.env", "CONFLUENCE.env")` and one `REMOTE_ENV_DIR = Path(r"\\syapp01\d$\sydoc\nexora\env")`. Task 2 makes the remote dir per file so `--push INT.env` / `--push STAGING.env` land in the new folders. Tests: `tests/unit/test_env_sync.py` (pure `diff_envs` tests — keep green, add one for the mapping).
- **`DB_GENERALI`** is `os.environ.get("DB_GENERALI", "Generali")` in `nx_lib/config.py` and is missing from `env/INT.env.example`, `env/PROD.env.example`, `env/STAGING.env.example` (only `TEST.env.example` has it). Staging needs it set to `Generali_STAGING`.
- **`db-migrate.py --env STAGING`** already exists (`docs/howto/db-migrations.md`: `--env INT|STAGING|PROD`). `nx -u --env:staging` exists too.
- **Migrations needed: NO** (no NexoraDB/GeneraliDB schema change). **i18n needed: NO** (no user-facing strings). **Deploy excludes:** `ops/` already ships; nothing new at top level. **New permission: none.**

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | `IS_PROD = os.environ.get("ENVIRONMENT") in ("PROD", "STAGING")` — one line, no new flag. | Staging must exercise the prod code paths (CSP, `/nexora` prefix, filesystem sessions, dev-route lockout). Every existing `IS_PROD` consumer wants the same answer for staging. |
| D2 | Reusable workflow `deploy-env.yml` + three caller jobs in `deploy.yml`; `pull_request` trigger dropped (every branch push already runs the test job and shows on the PR). | One copy of the deploy steps; no duplicate test runs per PR. |
| D3 | Dev deploys on **any** branch push except `main` (`github.ref_type == 'branch'`), same `paths` filter as today. | Owner choice (#338): no long-lived `develop`; dev = last push. |
| D4 | Prod deploys on `v*` tag push; test job runs on the tag too. | Owner choice (#338). |
| D5 | Staging redeploys nightly at **01:30** (`schedule` cron) after the 01:00 SQL refresh, so pending migrations are re-applied to the freshly restored copy. The 03:00 e2e schedule is untouched; e2e runs only for that cron or `workflow_dispatch`. | A restored PROD copy is at PROD schema; without this, staging runs `main` code on old schema every morning. |
| D6 | Deploys no longer stop/start `ngrok`/`cloudflared`. | Shared agent; stopping it would take prod down on every dev push. |
| D7 | `web.config` patched post-mirror (`value="PROD"` → env, `D:\sydoc\nexora` → folder) only when the target folder differs from prod. | Keeps the tracked file and its test unchanged. |
| D8 | Build stamp for non-prod includes the ref: `"<sha> (<ref_name>), <date>"`. | The footer is how you tell what dev/staging runs. |
| D9 | Staging DB names `nexora_STAGING`, `Generali_STAGING` on PRDSQL01, restored daily 01:00 by SQL Agent job `nexora - staging refresh` from a fresh `COPY_ONLY` backup in `D:\tmp\staging\`. | No durable `.bak` exists locally; COPY_ONLY leaves the real backup chain alone. |
| D10 | Only the two app-owned DBs are copied; vendor DBs shared read-only. | nexora opens no write transaction on the Octo/Statistics/MS02 engines. |
| D11 | Server setup is a script run over RDP once (`ops/setup-env.ps1`), not a workflow. | Owner choice; no WinRM. |
| D12 | Server env files are pushed with `scripts/env-sync.py --push INT.env` / `--push STAGING.env`; `STAGING.env` is derived locally from `PROD.env` by a script that swaps the two DB names and mints a fresh `FLASK_SECRET_KEY`. | Nobody pastes secrets; cookies cannot cross hosts. |

## Owner actions

1. **Before pushing this branch** (its first push deploys dev): RDP to SYAPP01 and run `ops/setup-env.ps1` twice (Task 6 tells you the exact commands) — the folders, pools, sites and ngrok endpoints must exist or the dev deploy fails at its preflight.
2. ngrok dashboard → Domains → add `dev-nexora.sydoc.ch` and `staging-nexora.sydoc.ch`; note each `....ngrok-cname.com` target. cyon DNS → CNAME `dev-nexora` and `staging-nexora` to those targets (same TTL as `nexora`). Targets (received 2026-09-14): `dev-nexora` → `3vvfskuc7isen9djp.zgzyk2x2s1c7jrr8.ngrok-cname.com`, `staging-nexora` → `62ubvmwfstncuu83.zgzyk2x2s1c7jrr8.ngrok-cname.com`; use them in `docs/howto/ngrok.md` (Task 8).
3. Copy `env/INT.env`, `env/TEST.env`, `env/PROD.env` into the worktree's `env/` before Task 7 (deny rule).
4. After merge to `main`: cut and push a `v*` tag promptly — **PROD no longer moves on merge**.
5. Confirm the ngrok plan line item after the first month (two custom domains ≈ $0.01/active-hour each).

---

# PHASE 0 — Config and env plumbing

### Task 1: `STAGING` behaves like `PROD`

**Files:**
- Modify: `nx_lib/config.py`
- Create: `tests/unit/test_is_prod_flag.py`

- [ ] **Step 1: Failing test.** Create `tests/unit/test_is_prod_flag.py`:

```python
"""IS_PROD must be true for STAGING too: staging is a public, prod-shaped host
(CSP, /nexora prefix, filesystem sessions, /dev/* lockout) -- #338."""

import importlib
import sys


def _is_prod_for(monkeypatch, value):
    monkeypatch.setenv("ENVIRONMENT", value)
    sys.modules.pop("nx_lib.config", None)
    return importlib.import_module("nx_lib.config").IS_PROD


def test_prod_and_staging_are_prod_shaped(monkeypatch):
    assert _is_prod_for(monkeypatch, "PROD") is True
    assert _is_prod_for(monkeypatch, "STAGING") is True


def test_int_and_test_are_not(monkeypatch):
    assert _is_prod_for(monkeypatch, "INT") is False
    assert _is_prod_for(monkeypatch, "TEST") is False
```

- [ ] **Step 2: Run it, expect the STAGING assertion to fail:** `python -m pytest tests/unit/test_is_prod_flag.py -q`
- [ ] **Step 3: Implement.** In `nx_lib/config.py` replace `IS_PROD = os.environ.get("ENVIRONMENT") == "PROD"` with:

```python
# STAGING is a public, prod-shaped host (#338): same CSP, /nexora prefix,
# filesystem sessions and /dev/* lockout as PROD.
IS_PROD = os.environ.get("ENVIRONMENT") in ("PROD", "STAGING")
```

- [ ] **Step 4: Green + the whole unit tier:** `python -m pytest tests/unit -q -p no:cacheprovider` (reimporting `nx_lib.config` in a test can upset module-level state — if other tests break, switch the helper to `subprocess.run([sys.executable, "-c", "import nx_lib.config as c; print(c.IS_PROD)"], env={**os.environ, "ENVIRONMENT": value})`).
- [ ] **Step 5: Commit.**

```
feat(config): treat STAGING as prod-shaped for IS_PROD gates (#338)

The staging host is public and must exercise the PROD code paths: Talisman
CSP, the /nexora prefix, filesystem sessions, secure cookies and the /dev/*
route lockout. One flag, one line; INT and TEST are unchanged.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

### Task 2: env examples + `env-sync.py` know the two new server files

**Files:**
- Modify: `env/INT.env.example`, `env/PROD.env.example`, `env/STAGING.env.example`
- Modify: `scripts/env-sync.py`
- Modify: `tests/unit/test_env_sync.py`
- Create: `scripts/make-staging-env.py`

- [ ] **Step 1: Example files.** In all three examples add, right after the `DB_NEXORA=` line, `DB_GENERALI=Generali` (INT, PROD) / `DB_GENERALI=Generali_STAGING` (STAGING). In `env/STAGING.env.example` change `DB_NEXORA=NexoraDB_STAGING` → `DB_NEXORA=nexora_STAGING`, `DB_STATISTICS=sydoc_stat_STAGING` → `DB_STATISTICS=SYDOC_Statistik`, `DB_OCTO_RUNTIME=OctoDB_STAGING` → `DB_OCTO_RUNTIME=RuntimeDatabase`, and add a comment line above them: `# Staging: app DBs are nightly PROD copies on PRDSQL01; vendor DBs are the PROD instances (read-only). See docs/howto/db-migrations.md.`
- [ ] **Step 2: Failing test.** Append to `tests/unit/test_env_sync.py`:

```python
def test_every_managed_file_has_a_remote_dir(env_sync):
    for name in ("PROD.env", "CONFLUENCE.env", "INT.env", "STAGING.env"):
        assert name in env_sync.MANAGED
        assert str(env_sync.remote_path(name)).lower().endswith(f"\\env\\{name}".lower())


def test_remote_dirs_are_per_environment(env_sync):
    assert r"\nexora\env" in str(env_sync.remote_path("PROD.env"))
    assert r"\nexora-dev\env" in str(env_sync.remote_path("INT.env"))
    assert r"\nexora-staging\env" in str(env_sync.remote_path("STAGING.env"))
```

- [ ] **Step 3: Run, expect `AttributeError: remote_path`.**
- [ ] **Step 4: Implement.** In `scripts/env-sync.py` replace the `REMOTE_ENV_DIR = ...` / `MANAGED = ("PROD.env", "CONFLUENCE.env")` pair with:

```python
_SERVER = Path(r"\\syapp01\d$\sydoc")
# file -> the deploy folder that owns it on SYAPP01 (#338: three hosts)
MANAGED = {
    "PROD.env": _SERVER / "nexora" / "env",
    "CONFLUENCE.env": _SERVER / "nexora" / "env",
    "INT.env": _SERVER / "nexora-dev" / "env",
    "STAGING.env": _SERVER / "nexora-staging" / "env",
}


def remote_path(name):
    return MANAGED[name] / name
```

  Then Grep every remaining `REMOTE_ENV_DIR` use in the file and switch it to `remote_path(name)`; the `MANAGED` membership checks (`if name not in MANAGED`) and `', '.join(MANAGED)` keep working on a dict. Update the module docstring's "Only these live on the server. INT/STAGING/TEST are dev-side" comment: INT.env and STAGING.env now also live on the server, in their own folders.
- [ ] **Step 5: Staging env generator.** Create `scripts/make-staging-env.py`:

```python
"""Derive env/STAGING.env from env/PROD.env without anyone reading secrets.

    python scripts/make-staging-env.py          # writes env/STAGING.env (refuses to overwrite)
    python scripts/make-staging-env.py --force

Swaps the two app-owned DB names to their *_STAGING copies (#338), sets
ENVIRONMENT=STAGING and mints a fresh FLASK_SECRET_KEY so staging cookies
can never be replayed against PROD. Everything else is copied verbatim.
"""

import argparse
import re
import secrets
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / "env"
SWAP = {
    "ENVIRONMENT": "STAGING",
    "DB_NEXORA": "nexora_STAGING",
    "DB_GENERALI": "Generali_STAGING",
    "FLASK_SECRET_KEY": None,  # minted below
}


def derive(prod_text):
    out, seen = [], set()
    for line in prod_text.splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=", line)
        key = m.group(1) if m else None
        if key in SWAP:
            seen.add(key)
            value = SWAP[key] if SWAP[key] is not None else secrets.token_urlsafe(48)
            line = f"{key}={value}"
        out.append(line)
    for key in SWAP.keys() - seen:  # PROD.env may lack DB_GENERALI (defaults to Generali)
        out.append(f"{key}={SWAP[key] or secrets.token_urlsafe(48)}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    dst = ENV / "STAGING.env"
    if dst.exists() and not a.force:
        raise SystemExit(f"{dst} exists; pass --force to overwrite")
    dst.write_text(derive((ENV / "PROD.env").read_text(encoding="utf-8")), encoding="utf-8")
    print(f"wrote {dst}")
```

  Add `tests/unit/test_make_staging_env.py` with one test: feed `derive("ENVIRONMENT=PROD\nDB_NEXORA=nexora\nFLASK_SECRET_KEY=old\nDB_UID=u\n")` and assert `ENVIRONMENT=STAGING`, `DB_NEXORA=nexora_STAGING`, `DB_GENERALI=Generali_STAGING` present, `DB_UID=u` untouched, `FLASK_SECRET_KEY=old` absent.
- [ ] **Step 6: Green:** `python -m pytest tests/unit/test_env_sync.py tests/unit/test_make_staging_env.py -q`; `ruff check scripts tests && ruff format --check scripts tests`.
- [ ] **Step 7: Commit.**

```
feat(env): map INT/STAGING env files to their SYAPP01 folders (#338)

env-sync.py learns one remote folder per managed file so `--push INT.env`
and `--push STAGING.env` land in D:\sydoc\nexora-dev and -staging.
make-staging-env.py derives STAGING.env from PROD.env (DB names swapped to
the *_STAGING copies, fresh FLASK_SECRET_KEY) so no secret is ever pasted.
Examples gain DB_GENERALI; STAGING.env.example now names the PROD vendor
DBs instead of never-existing *_STAGING copies.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

# PHASE 1 — CI: reusable deploy + three targets

### Task 3: Extract `deploy-env.yml` (reusable workflow)

**Files:**
- Create: `.github/workflows/deploy-env.yml`
- (deploy.yml is rewired in Task 4; until then the new file is inert)

- [ ] **Step 1: Create the file** by moving the whole `deploy:` job body out of `deploy.yml` into `.github/workflows/deploy-env.yml` with this frame and edits:

```yaml
name: Deploy (reusable)
on:
  workflow_call:
    inputs:
      env_name:      { required: true, type: string }   # INT | STAGING | PROD
      deploy_dir:    { required: true, type: string }   # D:\sydoc\nexora-dev ...
      app_pool:      { required: true, type: string }   # nexora-dev | nexora-staging | DefaultAppPool
      register_tasks: { required: false, type: boolean, default: false }

jobs:
  deploy:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      # ... the existing steps, edited as below ...
```

  Edits to the moved steps (Grep each anchor in the moved text):
  1. **"Verify prod env files"** → rename `Verify env files`; `$deployDir = "${{ inputs.deploy_dir }}"`; require `$deployDir` to exist (`throw "Deploy folder $deployDir does not exist -- run ops/setup-env.ps1 on SYAPP01 first (#338)"`); require the root `.env` to say `ENVIRONMENT=${{ inputs.env_name }}`; require `$deployDir\env\${{ inputs.env_name }}.env` to exist. Delete the legacy root `PROD.env` branch (`$legacyProdEnvFile`).
  2. **"Apply DB migrations to PROD"** → `Apply DB migrations (${{ inputs.env_name }})`; source `"${{ inputs.deploy_dir }}\env\${{ inputs.env_name }}.env"`, destination `"${{ github.workspace }}\env\${{ inputs.env_name }}.env"`; command `scripts/db-migrate.py --env ${{ inputs.env_name }} --yes`. Drop the legacy fallback.
  3. **"Stop app pool and service"** → `Stop app pool`; `$pool = "${{ inputs.app_pool }}"`; **delete** the `foreach ($tunnel in @('ngrok', 'cloudflared'))` block (D6) and its comment.
  4. **"Sync to deploy folder"**: `robocopy "${{ github.workspace }}" "${{ inputs.deploy_dir }}" /MIR ...` and every other `D:\sydoc\nexora` inside the step → `${{ inputs.deploy_dir }}` (the `*.env.example` sweep, the orphan sweep, the reporting-guide copy, the `var\` sweep, the build stamp path). Build stamp (D8):

     ```powershell
     $sha = "${{ github.sha }}".Substring(0, 7)
     $built = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
     $stamp = if ("${{ inputs.env_name }}" -eq "PROD") { "$sha, $built" } else { "$sha (${{ github.ref_name }}), $built" }
     Set-Content -Path "${{ inputs.deploy_dir }}\nx_lib\_build.py" -Encoding ASCII -Value "BUILD_STAMP = `"$stamp`""
     ```

  5. **New step after the sync, before the pool start** — `Patch web.config for this environment` (D7):

     ```powershell
     $ErrorActionPreference = 'Stop'
     $dir = "${{ inputs.deploy_dir }}"
     if ($dir -ieq 'D:\sydoc\nexora') { Write-Host 'PROD folder: tracked web.config used as-is'; exit 0 }
     $p = Join-Path $dir 'web.config'
     $xml = [System.IO.File]::ReadAllText($p)
     $xml = $xml.Replace('name="ENVIRONMENT" value="PROD"', 'name="ENVIRONMENT" value="${{ inputs.env_name }}"')
     $xml = $xml.Replace('D:\sydoc\nexora', $dir)
     [System.IO.File]::WriteAllText($p, $xml, [System.Text.UTF8Encoding]::new($false))
     Select-String -Path $p -Pattern 'ENVIRONMENT|PYTHONPATH|stdoutLogFile' | ForEach-Object { $_.Line.Trim() }
     ```

  6. **"Start app pool and service"** → `Start app pool`; `$pool = "${{ inputs.app_pool }}"`; delete the tunnel `foreach`.
  7. **"Register scheduled tasks"** → add `if: inputs.register_tasks`; keep the body (paths already hardcode `D:\sydoc\nexora\ops\...`, which is correct: tasks are prod-only).
- [ ] **Step 2: Lint the YAML** — `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy-env.yml', encoding='utf-8')); print('ok')"` (PyYAML is in the dev deps; if not, `uv run --with pyyaml python -c ...`). Also `Get-Content .github/workflows/deploy-env.yml | Select-String 'D:\\sydoc\\nexora[^-]'` must show **only** the `-ieq 'D:\sydoc\nexora'` guard and the three scheduled-task XML paths.
- [ ] **Step 3: Commit.**

```
ci(deploy): extract the deploy job into a reusable deploy-env.yml (#338)

Parameterised by env_name / deploy_dir / app_pool / register_tasks so the
same steps serve dev, staging and prod. Tunnel services are no longer
stopped around the mirror (one ngrok agent now fronts three sites; a
stopped app pool already answers 503). web.config is patched post-mirror
for non-prod folders; the build stamp names the ref on dev/staging.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

### Task 4: Rewire `deploy.yml` — triggers and three callers

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Triggers.** Replace the `on:` block: keep the `paths` list verbatim, but `push:` gets `branches: ["**"]` **and** `tags: ["v*"]` (paths filters are ignored for tags — good, a release always runs); **delete** the whole `pull_request:` block (D2); `schedule:` gains `- cron: "30 1 * * *"` above the existing `- cron: "0 3 * * 1-5"` with the comment `# 01:30 daily: redeploy main to STAGING after the 01:00 DB refresh on PRDSQL01 (re-applies pending migrations) -- #338`; keep `workflow_dispatch:`.
- [ ] **Step 2: Test job.** `concurrency.group` stays `test-${{ github.event.pull_request.number || github.ref }}` (the PR half is now dead but harmless — simplify to `test-${{ github.ref }}`). Change the Playwright install step's `if: github.event_name == 'pull_request'` to `if: github.event.schedule == '0 3 * * 1-5' || github.event_name == 'workflow_dispatch'`, and the e2e step's `if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'` to the same expression (D5 — the 01:30 cron must not run the 25-minute e2e).
- [ ] **Step 3: Replace the `deploy:` job** with three callers:

```yaml
  # dev = whatever topic branch was pushed last (#338)
  deploy-dev:
    needs: test
    if: github.event_name == 'push' && github.ref_type == 'branch' && github.ref != 'refs/heads/main'
    concurrency: { group: dev-deploy, cancel-in-progress: false }
    uses: ./.github/workflows/deploy-env.yml
    with: { env_name: INT, deploy_dir: 'D:\sydoc\nexora-dev', app_pool: nexora-dev }

  # staging = main, plus the nightly redeploy after the DB refresh
  deploy-staging:
    needs: test
    if: |
      (github.event_name == 'push' && github.ref == 'refs/heads/main') ||
      (github.event_name == 'schedule' && github.event.schedule == '30 1 * * *')
    concurrency: { group: staging-deploy, cancel-in-progress: false }
    uses: ./.github/workflows/deploy-env.yml
    with: { env_name: STAGING, deploy_dir: 'D:\sydoc\nexora-staging', app_pool: nexora-staging }

  # prod = a v* tag (CONTRIBUTING.md -> Releases)
  deploy-prod:
    needs: test
    if: github.event_name == 'push' && github.ref_type == 'tag' && startsWith(github.ref_name, 'v')
    concurrency: { group: prod-deploy, cancel-in-progress: false }
    uses: ./.github/workflows/deploy-env.yml
    with: { env_name: PROD, deploy_dir: 'D:\sydoc\nexora', app_pool: DefaultAppPool, register_tasks: true }
```

  Keep the existing "Deploys queue, never cancel" comment above the first caller. Note: the `schedule` event checks out the default branch (`main`) — exactly what staging wants.
- [ ] **Step 4: Update the header comment** in `deploy.yml` (the `# Inert-file changes skip the whole pipeline` block): mention that every branch push now runs the fast tier and deploys dev, `main` deploys staging, tags deploy prod.
- [ ] **Step 5: Lint** both YAML files as in Task 3 Step 2; `git grep -n "pull_request" .github/workflows/deploy.yml` → no hits.
- [ ] **Step 6: Commit.**

```
ci(deploy): branch pushes deploy dev, main deploys staging, tags deploy prod (#338)

deploy.yml keeps the test job and calls deploy-env.yml three times. The
pull_request trigger goes: every branch push already runs the fast tier and
its check shows on the PR. A 01:30 schedule redeploys main to staging after
the nightly DB refresh; e2e stays pinned to the 03:00 cron and dispatch.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

### Task 5: Move the tests that pin `deploy.yml` text

**Files:**
- Modify: `tests/unit/test_prune_active_sessions.py`, `tests/unit/test_prune_request_log.py`

- [ ] **Step 1: Run them, expect failures:** `python -m pytest tests/unit/test_prune_active_sessions.py tests/unit/test_prune_request_log.py -q` (the `/XD` line and `schtasks` text are no longer in `deploy.yml`).
- [ ] **Step 2: Fix.** In both files, every `"deploy.yml"` that is read for the robocopy `/XD` line or the `Register scheduled tasks` step becomes `"deploy-env.yml"`; docstrings that say "deploy.yml's robocopy /XD list" → "deploy-env.yml's". Add one assertion to `test_prune_active_sessions.py`'s task-registration test that `deploy.yml` passes `register_tasks: true` **exactly once** (`assert workflow_caller.count("register_tasks: true") == 1`, reading `deploy.yml`) — dev/staging must never register the prod tasks.
- [ ] **Step 3: Green:** same two files, then `python -m pytest tests/unit -q -p no:cacheprovider`.
- [ ] **Step 4: Commit.**

```
test(ci): follow the robocopy and task-registration steps into deploy-env.yml (#338)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

# PHASE 2 — Server and database

### Task 6: `ops/setup-env.ps1` — one-shot host setup (run by the owner over RDP)

**Files:**
- Create: `ops/setup-env.ps1`

- [ ] **Step 1: Write the script.** Parameters and behaviour (idempotent, `-WhatIf`-free, elevated PowerShell 5.1 on SYAPP01):

```powershell
<#
.SYNOPSIS  Create one extra nexora host on SYAPP01 (#338). Run elevated, once per env:
    .\setup-env.ps1 -Name dev     -Port 8081 -Environment INT     -Hostname dev-nexora.sydoc.ch
    .\setup-env.ps1 -Name staging -Port 8082 -Environment STAGING -Hostname staging-nexora.sydoc.ch
#>
param(
  [Parameter(Mandatory)][ValidateSet('dev','staging')] [string]$Name,
  [Parameter(Mandatory)][int]$Port,
  [Parameter(Mandatory)][ValidateSet('INT','STAGING')] [string]$Environment,
  [Parameter(Mandatory)][string]$Hostname,
  [string]$ProdDir = 'D:\sydoc\nexora',
  [string]$NgrokConfig = 'D:\sydoc\nexora\ngrok.yaml'
)
$ErrorActionPreference = 'Stop'
Import-Module WebAdministration
$dir  = "D:\sydoc\nexora-$Name"
$pool = "nexora-$Name"

# 1. folders (+ the per-request write paths, so Defender exclusion covers them from day one)
foreach ($d in @($dir, "$dir\var", "$dir\var\logs\system", "$dir\var\logs\user", "$dir\var\session", "$dir\env")) {
  if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}
# 2. root env selector (robocopy /XF *.env never touches it)
Set-Content -Path "$dir\.env" -Value "ENVIRONMENT=$Environment" -Encoding ASCII

# 3. app pool, cloned from DefaultAppPool's identity settings
if (-not (Test-Path "IIS:\AppPools\$pool")) { New-WebAppPool -Name $pool | Out-Null }
$src = Get-ItemProperty 'IIS:\AppPools\DefaultAppPool'
Set-ItemProperty "IIS:\AppPools\$pool" -Name managedRuntimeVersion -Value ''   # no CLR: HttpPlatformHandler only
Set-ItemProperty "IIS:\AppPools\$pool" -Name processModel.identityType -Value $src.processModel.identityType
if ($src.processModel.identityType -eq 'SpecificUser') {
  Write-Warning "DefaultAppPool runs as $($src.processModel.userName); set the same user+password on IIS:\AppPools\$pool by hand."
}
$acct = if ($src.processModel.identityType -eq 'SpecificUser') { $src.processModel.userName } else { "IIS AppPool\$pool" }
icacls $dir /grant "${acct}:(OI)(CI)M" /T | Out-Null

# 4. site bound to loopback only -- ngrok is the only client
if (-not (Get-Website -Name $pool -ErrorAction SilentlyContinue)) {
  New-Website -Name $pool -PhysicalPath $dir -ApplicationPool $pool -IPAddress 127.0.0.1 -Port $Port | Out-Null
}
# 5. runner service account needs to mirror into $dir and restart the pool
$runner = (Get-CimInstance Win32_Service -Filter "Name LIKE 'actions.runner.%'").StartName
if ($runner) { icacls $dir /grant "${runner}:(OI)(CI)F" /T | Out-Null } else { Write-Warning 'GitHub runner service not found; grant its account Full on $dir by hand.' }

# 6. Defender: per-request writes under var\ (see memory: project_syapp01_defender_exclusion)
if (-not ((Get-MpPreference).ExclusionPath -contains "$dir\var")) { Add-MpPreference -ExclusionPath "$dir\var" }

# 7. ngrok endpoint (append once; never echo the file -- it holds the authtoken)
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
}
Write-Host "OK: $dir | pool $pool | 127.0.0.1:$Port | ENVIRONMENT=$Environment | https://$Hostname"
Write-Host "Next: push env/$Environment.env with scripts/env-sync.py --push $Environment.env, then push a branch (dev) / merge main (staging)."
```

  Notes to keep in the script header: the `endpoints:` list in `ngrok.yaml` must be the **last** top-level key for `Add-Content` to append into it (it is today — `agent:` then `endpoints:`); if the owner reorders the file, edit by hand. The bot-blocking `traffic_policy` is deliberately not copied to dev/staging.
- [ ] **Step 2: Parse check** on the dev box: `powershell -NoProfile -Command "[scriptblock]::Create((Get-Content ops/setup-env.ps1 -Raw)) | Out-Null; 'parses'"`.
- [ ] **Step 3: Copy to the server for the owner:** `Copy-Item ops/setup-env.ps1 \\syapp01\d$\sydoc\tools\setup-env.ps1` (tools\ is outside the mirror). Tell the owner the two commands from the synopsis.
- [ ] **Step 4: Commit.**

```
feat(ops): setup-env.ps1 creates a dev/staging host on SYAPP01 (#338)

Idempotent, run once per environment over RDP: folder + var\ tree, root
.env selector, app pool cloned from DefaultAppPool, loopback-only IIS site,
runner and pool ACLs, Defender exclusion on var\, and the ngrok endpoint
appended to ngrok.yaml with a service restart.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

### Task 7: Staging databases — nightly refresh job on PRDSQL01

**Files:**
- Create: `ops/staging-refresh.sql`

- [ ] **Step 1: Write the job script** `ops/staging-refresh.sql` (idempotent: drops and recreates the job; the step body is what runs nightly):

```sql
-- nexora staging refresh (#338): copy the two app-owned PROD databases to
-- *_STAGING every night at 01:00. COPY_ONLY leaves the real backup chain
-- (sqlBackuper.ps1 -> Azure) untouched. Install once, as sysadmin:
--   sqlcmd -S PRDSQL01\PRDSQL01 -U <DB_UID> -P <DB_PWD> -i ops/staging-refresh.sql
-- Re-running reinstalls the job. Run it now: EXEC msdb.dbo.sp_start_job N'nexora - staging refresh';
USE msdb;
GO
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'nexora - staging refresh')
    EXEC msdb.dbo.sp_delete_job @job_name = N'nexora - staging refresh';
GO
EXEC msdb.dbo.sp_add_job @job_name = N'nexora - staging refresh', @description = N'nexora #338: COPY_ONLY backup of nexora + Generali, restore as *_STAGING. Runs before the 01:30 staging redeploy in GitHub Actions.';
GO
EXEC msdb.dbo.sp_add_jobstep @job_name = N'nexora - staging refresh', @step_name = N'refresh', @subsystem = N'TSQL', @database_name = N'master', @command = N'
SET NOCOUNT ON;
IF NOT EXISTS (SELECT 1 FROM sys.dm_os_enumerate_filesystem(''D:\tmp'', ''staging'') WHERE is_directory = 1)
    EXEC master.sys.xp_create_subdir ''D:\tmp\staging'';
DECLARE @pairs TABLE (src sysname, dst sysname);
INSERT @pairs VALUES (N''nexora'', N''nexora_STAGING''), (N''Generali'', N''Generali_STAGING'');
DECLARE @src sysname, @dst sysname, @bak nvarchar(260), @sql nvarchar(max), @move nvarchar(max);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT src, dst FROM @pairs;
OPEN c; FETCH NEXT FROM c INTO @src, @dst;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @bak = N''D:\tmp\staging\'' + @src + N''.bak'';
    SET @sql = N''BACKUP DATABASE '' + QUOTENAME(@src) + N'' TO DISK = @bak WITH COPY_ONLY, INIT, COMPRESSION, CHECKSUM;'';
    EXEC sp_executesql @sql, N''@bak nvarchar(260)'', @bak = @bak;
    -- MOVE every file of the source to a *_STAGING file name (same server, so the
    -- source''s logical names ARE the backup''s logical names -- no FILELISTONLY needed)
    SELECT @move = STRING_AGG(CAST(N''MOVE '' + QUOTENAME(name, '''''''') + N'' TO '' + QUOTENAME(
        CASE type_desc WHEN N''LOG'' THEN N''D:\log\'' ELSE N''D:\data\'' END + @dst + N''_'' + CAST(file_id AS nvarchar(3))
        + CASE type_desc WHEN N''LOG'' THEN N''.ldf'' ELSE N''.mdf'' END, '''''''') AS nvarchar(max)), N'', '')
    FROM sys.master_files WHERE database_id = DB_ID(@src);
    IF DB_ID(@dst) IS NOT NULL
        EXEC(N''ALTER DATABASE '' + @dst + N'' SET SINGLE_USER WITH ROLLBACK IMMEDIATE'');
    SET @sql = N''RESTORE DATABASE '' + QUOTENAME(@dst) + N'' FROM DISK = @bak WITH REPLACE, RECOVERY, CHECKSUM, '' + @move + N'';'';
    EXEC sp_executesql @sql, N''@bak nvarchar(260)'', @bak = @bak;
    EXEC(N''ALTER DATABASE '' + QUOTENAME(@dst) + N'' SET MULTI_USER'');
    EXEC(N''ALTER DATABASE '' + QUOTENAME(@dst) + N'' SET RECOVERY SIMPLE'');   -- disposable copy: no log growth
    EXEC master.sys.xp_delete_files @bak;
    FETCH NEXT FROM c INTO @src, @dst;
END
CLOSE c; DEALLOCATE c;
', @on_success_action = 1, @on_fail_action = 2;
GO
EXEC msdb.dbo.sp_add_jobschedule @job_name = N'nexora - staging refresh', @name = N'daily 01:00', @freq_type = 4, @freq_interval = 1, @active_start_time = 010000;
GO
EXEC msdb.dbo.sp_add_jobserver @job_name = N'nexora - staging refresh';
GO
```

  Keep `QUOTENAME(..., '''')` semantics in mind when editing: the whole step is one `N'...'` literal, so every inner quote is doubled. `xp_delete_files` needs SQL 2019+ (PRDSQL01 is 2022). `STRING_AGG` needs compat ≥ 140 on `master` — check with `SELECT compatibility_level FROM sys.databases WHERE name='master'`; if lower, build `@move` with `FOR XML PATH('')` instead.
- [ ] **Step 2: Install.** From the dev box (owner has `env/PROD.env` in place; the login is sysadmin):

```powershell
$e = Get-Content env\PROD.env | ConvertFrom-StringData
sqlcmd -S "$($e.DB_SERVER_PRD)" -U $e.DB_UID -P $e.DB_PWD -b -i ops\staging-refresh.sql
```

  (`ConvertFrom-StringData` chokes on `=` inside values — if it does, read the three keys with `Select-String '^DB_(SERVER_PRD|UID|PWD)='` instead. Never echo `$e`.)
- [ ] **Step 3: First run + verify:** `sqlcmd ... -Q "EXEC msdb.dbo.sp_start_job N'nexora - staging refresh'"`, then poll `SELECT TOP 1 run_status, run_duration, message FROM msdb.dbo.sysjobhistory h JOIN msdb.dbo.sysjobs j ON j.job_id=h.job_id WHERE j.name='nexora - staging refresh' AND step_id=0 ORDER BY run_date DESC, run_time DESC` until `run_status = 1`. Then `SELECT name, state_desc, user_access_desc, recovery_model_desc FROM sys.databases WHERE name LIKE '%_STAGING'` → two rows, `ONLINE`, `MULTI_USER`, `SIMPLE`. Record the duration in the Gotchas section of this plan (expected: a few minutes for ~3.5 GB).
- [ ] **Step 4: Migrations rehearsal:** after the owner copied `env/PROD.env` into the worktree, `python scripts/make-staging-env.py` then `python scripts/db-migrate.py --env STAGING --dry-run` — must list exactly the migrations PROD lacks vs `main` (usually none), then `--yes` to apply. This is what the 01:30 job will do every night.
- [ ] **Step 5: Push env files to SYAPP01** (needs Task 6 done by the owner so the folders exist): `python scripts/env-sync.py --push STAGING.env` and `python scripts/env-sync.py --push INT.env`. Then `python scripts/env-sync.py` (report) must show no missing keys for any managed file. `INT.env` on the dev box is the source for the dev host; confirm it has no dev-box-only absolute paths (`Select-String 'C:\\' env\INT.env` → nothing).
- [ ] **Step 6: Commit** (only `ops/staging-refresh.sql`; env files are gitignored).

```
feat(ops): nightly PRDSQL01 job restores PROD app DBs as *_STAGING (#338)

COPY_ONLY backup of nexora and Generali to D:\tmp\staging, RESTORE WITH
REPLACE + MOVE to nexora_STAGING / Generali_STAGING at 01:00, recovery
SIMPLE, backup file deleted. The 01:30 staging redeploy then re-applies
whatever migrations main carries beyond PROD -- a nightly rehearsal on
real data.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

# PHASE 3 — Docs and changelog

### Task 8: Documentation sweep

**Files:**
- Modify: `docs/howto/ngrok.md`, `docs/howto/cloudflare-tunnel.md`, `docs/howto/iis.md`, `docs/howto/db-migrations.md`, `docs/howto/outage-monitor.md`, `CONTRIBUTING.md`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`

- [ ] **Step 1: `docs/howto/ngrok.md`** — delete the `> **Being replaced by Cloudflare Tunnel**` banner; add a "Three endpoints" table (host → port → folder → env → what deploys it), the `ngrok.yaml` shape (three `endpoints:` entries, authtoken redacted), the cyon CNAME rows (`dev-nexora` → `3vvfskuc7isen9djp.zgzyk2x2s1c7jrr8.ngrok-cname.com`, `staging-nexora` → `62ubvmwfstncuu83.zgzyk2x2s1c7jrr8.ngrok-cname.com`; prod's `nexora` → `dzpsykqcwgqzfk1c.zgzyk2x2s1c7jrr8.ngrok-cname.com`), and a pointer to `ops/setup-env.ps1`. Keep the manual-run and service-install commands.
- [ ] **Step 2: `docs/howto/cloudflare-tunnel.md`** — insert under the title: `> **Parked (2026-09-14, #338).** A \`nexora.sydoc.ch\` sub-zone is Enterprise-only on Cloudflare, and moving the whole \`sydoc.ch\` zone is rejected (company mail and other cyon-hosted services). ngrok stays; dev/staging hosts are extra ngrok endpoints — \`docs/howto/ngrok.md\`. This doc is kept as the recipe should the zone move ever be approved.`
- [ ] **Step 3: `docs/howto/iis.md`** — add a section "Three sites" listing `DefaultAppPool`/port 80/`D:\sydoc\nexora`, `nexora-dev`/127.0.0.1:8081/`D:\sydoc\nexora-dev`, `nexora-staging`/127.0.0.1:8082/`D:\sydoc\nexora-staging`; note that `web.config` is patched post-mirror by `deploy-env.yml` for the two extra folders.
- [ ] **Step 4: `docs/howto/db-migrations.md`** — near `--env INT|STAGING|PROD`, a "STAGING" subsection: the databases, the 01:00 refresh job (`ops/staging-refresh.sql`), the 01:30 redeploy that re-applies migrations, the consequence (a non-idempotent migration fails on staging first — that is the point), and that PROD schema now moves only on a `v*` tag deploy.
- [ ] **Step 5: `docs/howto/outage-monitor.md`** — the sentence at `every push to \`main\`** — the "Register scheduled tasks" step` → "every PROD deploy (a `v*` tag push)". Add: the monitor's public-site probe should also watch the two new hosts — open a follow-up issue rather than doing it here (YAGNI until they misbehave).
- [ ] **Step 6: `CONTRIBUTING.md` → Releases** — replace `Deploy is not tied to the tag — **every** push to \`main\` deploys (see \`README.md\`). The tag is a label on what shipped...` with: `main` deploys **staging** (`staging-nexora.sydoc.ch`); the tag push **is** the PROD deploy; any other branch push deploys **dev**. Keep the tag recipe.
- [ ] **Step 7: `README.md`** — the line `**Every** merge to \`main\` deploys; a release tag (\`v3.2.5\`) only labels what shipped and does not trigger anything.` → "Every merge to `main` deploys **staging**; a `v*` tag deploys **PROD**; every other branch push deploys **dev** (`dev-nexora.sydoc.ch`)." Add the three hosts to the environment section if one exists (Grep `nexora.sydoc.ch`).
- [ ] **Step 8: `CLAUDE.md`** — (a) "Environment & running": add one line `**Hosted envs:** dev-nexora (any branch push, INT DBs) · staging-nexora (main, nightly PROD copies) · nexora (v* tag). Deploy steps: \`.github/workflows/deploy-env.yml\`; host setup: \`ops/setup-env.ps1\`; see \`docs/howto/ngrok.md\`.` (b) The footer paragraph: `Every merge to \`main\` deploys, but the version only moves when someone cuts a release` → "Every merge to `main` deploys **staging**; PROD moves only when someone pushes a `v*` tag, so the tag is both the release and the deploy". (c) "Deploy artifacts": `deploy.yml` → `deploy-env.yml` where the robocopy exclude list is mentioned. (d) "Public tunnel" line: drop "Cloudflare Tunnel prepared, cutover pending", say "ngrok (three endpoints, `docs/howto/ngrok.md`); Cloudflare parked (`docs/howto/cloudflare-tunnel.md`)".
- [ ] **Step 9: `CHANGELOG.md` → `[Unreleased]`**:
  - Added: "Hosted **dev** (`dev-nexora.sydoc.ch`, last pushed branch, INT databases) and **staging** (`staging-nexora.sydoc.ch`, `main`, nightly PROD-copy databases) environments on SYAPP01 behind the existing ngrok agent; `ops/setup-env.ps1`, `ops/staging-refresh.sql`, `scripts/make-staging-env.py` (#338)."
  - Changed: "**PROD now deploys on a `v*` tag push, not on merge to `main`**; `main` deploys staging. The deploy steps moved to the reusable `.github/workflows/deploy-env.yml`; deploys no longer stop the ngrok service (#338)." / "`STAGING` is prod-shaped: CSP, `/nexora` prefix, filesystem sessions, `/dev/*` lockout (#338)." / "`scripts/env-sync.py` manages `INT.env` and `STAGING.env` in their SYAPP01 folders; `DB_GENERALI` added to the env examples (#338)."
  - Removed: "The `pull_request` trigger on `deploy.yml` — every branch push runs the fast test tier (#338)."
- [ ] **Step 10: Stale-reference sweep:** `git grep -n "every push to .main\|Every merge to .main\|merge to .main. deploys" -- README.md CLAUDE.md CONTRIBUTING.md docs` → only the rewritten lines. `git grep -n "cloudflared" -- .github` → none (D6). The `confluence-docs.yml` sync publishes `docs/howto/*` — nothing to do.
- [ ] **Step 11: Commit.**

```
docs: three hosted environments, tag-deploys-prod, ngrok stays (#338)

ngrok.md gains the dev/staging endpoints and cyon records; the Cloudflare
tunnel doc is parked with the reason; iis.md lists the three sites;
db-migrations.md explains the nightly STAGING refresh and migration
rehearsal; CONTRIBUTING/README/CLAUDE.md now say main -> staging and
tag -> PROD. Changelog under [Unreleased].

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

## Verification (after the owner ran Task 6 and the branch is pushed)

- [ ] Actions → the push run: `test` green, `deploy-dev` green; `https://dev-nexora.sydoc.ch/login` → 200, footer shows `<sha> (<branch>), <date>`; `/dev/login/ben.streich` → 404 (loopback-only guard). `\\syapp01\d$\sydoc\nexora-dev\web.config` says `ENVIRONMENT=INT` and `PYTHONPATH=D:\sydoc\nexora-dev`.
- [ ] After merge: `deploy-staging` green; `https://staging-nexora.sydoc.ch/nexora/login` → 200 with the CSP header present (`curl -sI ... | Select-String content-security-policy`), footer `<sha> (main), <date>`, log in, open a workitem and a report against the `_STAGING` data. The 01:30 run the next night is green and `sys.databases` shows the two `_STAGING` DBs re-created (fresh `create_date`).
- [ ] After the first `v*` tag: `deploy-prod` green, PROD footer stamp changes, `schtasks /query /tn "\sydoc\nexora\Outage Monitor"` still present. A later merge to `main` does **not** change the PROD stamp.
- [ ] `ngrok` service was never restarted by a deploy (`Get-EventLog -LogName System -Source 'Service Control Manager' -Newest 50 | ? Message -match ngrok`).

## Gotchas & notes

- **Ordering trap:** the first push of this branch triggers `deploy-dev`; if `D:\sydoc\nexora-dev` does not exist yet the job fails at "Verify env files" — harmless, re-run after `setup-env.ps1`. Same for `main` → `nexora-staging`.
- **PROD freeze after merge:** until someone pushes a `v*` tag, PROD keeps the pre-merge build. Cut the release the same day (Owner action 4).
- **01:00–01:35 window:** a merge to `main` landing while the SQL job holds `nexora_STAGING` in `SINGLE_USER` fails at the migration step; re-run the workflow. Rare; not worth a lock.
- **Restored SchemaMigrations:** `*_STAGING` carries PROD's `dbo.SchemaMigrations`. Migrations `main` has beyond PROD are re-applied at 01:30 — so they must be idempotent (house rule) or they fail on staging first. Good.
- **Interactive mails from staging:** password-reset mails (`nx_lib/mail.py::send_mail`) go to real addresses; scheduled reports and outage alerts do **not** run there (tasks are prod-only). If someone complains, add `MAIL_ENABLED=0` handling — YAGNI for now.
- **"Switch user" UI** stays hidden on staging (IS_PROD) and visible on dev, where `_dev_route_forbidden` 404s every non-loopback call — cosmetic only.
- **ngrok.yaml append:** `Add-Content` assumes `endpoints:` is the last top-level key (true today). The authtoken lives in that file: never `Get-Content` it into a transcript.
- **`schedule` events checkout `main`**, so the 01:30 job always redeploys `main` — never a branch.
- **PRDSQL01 disk:** the COPY_ONLY files are compressed and deleted after restore; peak extra space ≈ backup + restored copies ≈ 3× the app DBs (~10 GB) against ~700 GB free.
- **Memory drift:** memory notes claim INT DBs are named `NexoraDB_INT`; the real env files use the same names (`nexora`, `Generali`) on a different server (`INTSQL01`). Update the memory when this lands.
- **Parking, not deleting:** `docs/howto/cloudflare-tunnel.md` and the pre-staged `D:\sydoc\tools\cloudflared` stay; the deploy workflow no longer references `cloudflared`.
