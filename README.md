# nexora

Internal Sydoc portal: workitems, invoices, chat, admin, tenant-specific pages.
Flask 3 / Python 3.13 / SQL Server / IIS (PROD).

## Quick start

```powershell
# 1. Clone to a short path (not OneDrive)
git clone https://github.com/Sydoc-Code/nexora.git C:\dev\nexora
cd C:\dev\nexora

# 2. Set up Python venv and dependencies (uv)
pip install uv
uv venv
uv sync
python -m playwright install chromium

# 3. Copy env templates
copy env\INT.env.example env\INT.env    # then fill in real values
copy env\TEST.env.example env\TEST.env

# 4. Reset the NEXORA_TEST database
.\scripts\test-db-reset.ps1

# 5. Install git hooks (pre-commit framework)
.venv\Scripts\pre-commit.exe install --install-hooks
.venv\Scripts\pre-commit.exe install --hook-type commit-msg
.venv\Scripts\pre-commit.exe install --hook-type pre-push

# 6. Run the dev server
$env:ENVIRONMENT = "INT"
python nx_main.py
```

> A one-shot `bootstrap.ps1` is coming in a later PR; until then the steps above are the path.

## Running tests

```powershell
python -m pytest tests -v --reruns 2 --only-rerun flaky_e2e
```

The pre-push hook runs the same command on every `git push`. Bypass with `--no-verify` (CI still gates deploy).

## Deploy

Push to `main` → GitHub Actions runs the `test` job → if green, the `deploy` job mirrors the repo to IIS on SYAPP01 and applies any pending SQL migrations. See `.github/workflows/deploy.yml` and `docs/howto/iis.md`.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for naming, branch, and commit conventions.
