Documentation is available here: https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774

## Running tests

Tests live in `tests/` (`unit/`, `integration/`, `e2e/`) and run against a dedicated `NEXORA_TEST` SQL Server database. The full suite runs in ~12 seconds locally.

### One-time setup

1. Install dev dependencies:
   ```powershell
   pip install -r requirements-dev.txt
   python -m playwright install chromium
   ```
2. Apply the NEXORA_TEST DDL block from `environment_transfer_queries.tmp.sql` to the SQL Server (creates the database + scoped login).
3. Copy `TEST.env.example` to `TEST.env` and fill in your test SQL Server credentials.
4. Reset NEXORA_TEST to a clean state:
   ```powershell
   .\scripts\test-db-reset.ps1
   ```
5. Install the local pre-push git hook:
   ```powershell
   .\scripts\install-hooks.ps1
   ```

### Running tests locally

```powershell
python -m pytest tests -v --reruns 2 --only-rerun flaky_e2e
```

The pre-push hook runs the same command on every `git push`. Bypass it with `git push --no-verify` (CI will still gate the deploy).

### CI

Pushes to `main` run the `test` job in `.github/workflows/deploy.yml`. If it fails, the `deploy` job is skipped. The `test` job also runs on pull requests against `main` so the gate is verified before merging, but the `deploy` job only runs on push-to-main. Test reports (`junit.xml`, `report.html`) are uploaded as a workflow artifact named `test-results`.
