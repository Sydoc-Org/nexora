# nexora

Internal Sydoc portal: workitems, reporting, admin, tenant-specific pages.
Flask 3 / Python 3.13 / SQL Server / IIS (PROD).

## Quick start

```powershell
git clone https://github.com/Sydoc-Org/nexora.git C:\dev\nexora    # not under OneDrive
cd C:\dev\nexora
.\bootstrap.ps1
# follow the printed checklist (edit env\INT.env, reset NEXORA_TEST, etc.)
```

For setup details — what bootstrap does and how to do each step by hand if it fails — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Running tests

```powershell
python -m pytest tests -v
```

E2E browser tests are automatically retried up to twice on failure (armed in `tests/e2e/conftest.py`); unit and integration tests fail fast with no retries.

`git push` runs no tests locally any more; the pre-push hook only guards branch names. CI runs the fast tier (everything except `tests/e2e`) on every PR and on `main`, and the e2e browser tier nightly on `main` and on demand (Actions → Deploy → Run workflow), with a 25-minute hard timeout. Docs-only pushes to `main` (`docs/`, `*.md`, `.claude/`) skip the CI pipeline entirely.

## Deploy

Push to `main` → GitHub Actions runs the `test` job → if green, the `deploy` job mirrors the repo to IIS on SYAPP01 and applies any pending SQL migrations. See `.github/workflows/deploy.yml` and `docs/howto/iis.md`.

Changes land through a PR from a short-lived topic branch, never a direct push to `main` — by convention, since branch protection is unavailable on this repo's plan. **Every** merge to `main` deploys; a release tag (`v3.2.5`) only labels what shipped and does not trigger anything. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the branching, parallel-work and release rules.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for naming, branch, and commit conventions.
