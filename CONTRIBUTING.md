# Contributing to nexora

Internal Sydoc project. Read this once before opening your first PR.

## Prerequisites

- Windows 10/11 with PowerShell 7+
- Python 3.13.9 (see `.python-version`)
- SQL Server access to `NEXORA_TEST` (test DB) and credentials for INT/PROD DBs
- A clone of the repo at a short path (e.g. `C:\dev\nexora`, **not** under OneDrive)

## One-time setup

Run the bootstrap script — idempotent, re-runnable, handles every step below:

```powershell
.\bootstrap.ps1                # default: INT environment
.\bootstrap.ps1 -Env STAGING   # if you target staging instead
```

Then follow the checklist it prints: edit your `env\*.env` files with real credentials, reset `NEXORA_TEST` via `.\scripts\test-db-reset.ps1`, and start the dev server with `.\bin\nx.ps1 -u`. The `nx` CLI does a lot more than start the server (status, logs, route listing, browser auto-login, `--doctor` preflight, an interactive TUI) — see `docs/howto/nx.md` for the full reference.

### Manual fallback

If bootstrap fails (or you want to know what it does), the manual steps are:

```powershell
pip install uv
uv venv
uv sync
python -m playwright install chromium

copy env\INT.env.example env\INT.env       # then fill in real values
copy env\TEST.env.example env\TEST.env

.venv\Scripts\pre-commit.exe install --install-hooks
.venv\Scripts\pre-commit.exe install --hook-type commit-msg
.venv\Scripts\pre-commit.exe install --hook-type pre-push
```

The repo still ships `requirements.txt` and `requirements-dev.txt` (generated from `uv.lock`); they exist for the IIS/wfastcgi deploy path on SYAPP01. Locally, bare `uv sync` is the whole setup — dev deps are a PEP 735 `[dependency-groups]` group that uv installs by default, so no `--extra` flag exists anymore.

**Adding a dependency.** `pyproject.toml` is the only source of truth. Never
hand-edit `requirements*.txt` — they are regenerated from `uv.lock` and your
edit is both silently discarded on the next export and invisible to `uv sync`,
so every other checkout gets `ModuleNotFoundError` while your machine keeps
working off an ad-hoc install. The correct sequence:

```
# 1. add to [project.dependencies] (runtime) or [dependency-groups].dev
uv lock
uv sync
uv export --format requirements-txt --no-hashes --no-dev -o requirements.txt
uv export --format requirements-txt --no-hashes          -o requirements-dev.txt
```

`tests/unit/test_dependencies.py` fails if `nx_lib/`, `scripts/` or `ops/`
imports a package that `pyproject.toml` does not declare.

## Naming conventions

**Python:**
- Functions, methods, variables, module names: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE`
- Enforced via `ruff check --select N` (after PR 2)

**Templates (Jinja2):**
- Page templates: `snake_case.html` (e.g. `workitem_detail.html`)
- Paired JS partials: `templates/js/_<page>_js.html`
- Includes/partials: `_underscore_prefixed.html`

**SQL (documentation-only, not lint-enforced):**
- Tables: `PascalCase` (e.g. `Users`)
- Stored procs: `sp` + `PascalCase` (e.g. `spGetUserPermissions`)
- Functions: `fn` + `PascalCase`
- Migration files: `NNNN_short_snake_case.sql`

**Branches:**
- `feature/<version>` — release-track work (e.g. `feature/2.5.60`)
- `fix/<short-kebab-topic>` — isolated bug fix
- `chore/<short-kebab-topic>` — tooling, deps, refactors with no behaviour change
- `refactor/<short-kebab-topic>` — structural change with no behaviour change
- `hotfix/<version>` — emergency PROD fix

**Commits — Conventional Commits:**
- `feat: <subject>` — new user-facing feature
- `fix: <subject>` — bug fix
- `chore: <subject>` — tooling, deps, no behaviour change
- `refactor: <subject>` — code restructure, no behaviour change
- `docs: <subject>` — documentation only
- `test: <subject>` — test-only changes
- `ci: <subject>` — CI/CD changes
- Optional scope: `feat(dashboard): …`
- Subject in imperative ("add X", not "added X")
- Body explains why

## Pull requests

- Target `main`
- Pre-push hook runs the test suite; CI re-runs it before deploy
- Keep PRs small and focused. The repo prefers many small PRs over one large one.
