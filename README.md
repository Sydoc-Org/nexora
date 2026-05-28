# nexora

Internal Sydoc portal: workitems, invoices, chat, admin, tenant-specific pages.
Flask 3 / Python 3.13 / SQL Server / IIS (PROD).

## Quick start

```powershell
git clone https://github.com/Sydoc-Code/nexora.git C:\dev\nexora    # not under OneDrive
cd C:\dev\nexora
.\bootstrap.ps1
# follow the printed checklist (edit env\INT.env, reset NEXORA_TEST, etc.)
```

For setup details — what bootstrap does and how to do each step by hand if it fails — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Running tests

```powershell
python -m pytest tests -v --reruns 2 --only-rerun flaky_e2e
```

The pre-push hook runs the same command on every `git push`. Bypass with `--no-verify` (CI still gates deploy).

## Deploy

Push to `main` → GitHub Actions runs the `test` job → if green, the `deploy` job mirrors the repo to IIS on SYAPP01 and applies any pending SQL migrations. See `.github/workflows/deploy.yml` and `docs/howto/iis.md`.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for naming, branch, and commit conventions.
