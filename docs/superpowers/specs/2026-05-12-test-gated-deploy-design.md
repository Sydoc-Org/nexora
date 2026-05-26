**Test-gated deploy — design spec**

Date: 2026-05-12
Status: Draft, pending user review
Owner: benstreich

**Goal**

Make every deploy to PROD depend on a passing test suite. Today `.github/workflows/deploy.yml` runs on every push to `main` with no test step — a typo can ship straight to prod. After this work, no test pass → no deploy.

The first round covers infrastructure plus enough tests to make the gate real (not just a placeholder). Coverage grows in follow-up PRs.

**Scope — this PR**

In scope:

- pytest installed and configured with JUnit + HTML reports under `test-results/`
- A `tests/` tree with `unit/`, `integration/`, and `e2e/` subdirs
- `TEST.env` pattern (parallel to `INT.env` / `PROD.env`) plus committed `TEST.env.example`
- A dedicated `NEXORA_TEST` SQL Server database with reproducible schema + seed
- Initial test inventory: ~5 unit tests, ~4 integration tests, 1 Playwright E2E smoke (login + 2FA + dashboard)
- GitHub Actions: a `test` job that runs on the same self-hosted runner; `deploy` is `needs: test`. If `test` fails or is skipped, `deploy` does not run.
- A `scripts/install-hooks.ps1` that installs a local `pre-push` hook running the fast tiers (unit + integration). E2E is CI-only locally.
- Strict failure policy: any failing test in any tier blocks deploy. E2E flakes are addressed via `--retries=2` at the pytest invocation, not by downgrading the gate.

Out of scope (deferred to later PRs):

- Coverage targets / minimum line-coverage gate
- Tests for `admin`, `dashboard`, `workitems`, `chat`, `invoices`, `notifications`, `profile`, `generali`, `core` view modules beyond the smoke pieces
- Integration tests against `engineOctoDB`, `engineStatisticsDB`, `engineGeneraliDB` (these stay un-exercised in round 1; engines created lazily by SQLAlchemy so tests don't actually touch them)
- Mocking Microsoft Graph / Octopus / Bexio external services (round-1 tests do not invoke flows that call them)
- Performance tests, load tests, security scans
- Reporting to anything outside the GitHub Actions UI

**Architecture**

Test layers follow the testing pyramid — wide at the base (unit), narrower in the middle (integration), single test on top (E2E).

```
tests/
├── conftest.py           # shared fixtures (app, client, db_session, test_users)
├── unit/
│   ├── test_security.py        # has_permission, require_permission decorator logic
│   ├── test_files.py           # is_file_allowed with libmagic
│   ├── test_i18n.py            # get_locale priority order
│   └── test_password.py        # bcrypt hash/verify (if helper exists, else skip)
├── integration/
│   ├── test_auth_flow.py       # GET /login 200; POST /login + 2FA; bad creds; rate-limited
│   ├── test_permission_guard.py # protected route returns 403 for unauthorised
│   └── test_health.py          # GET /healthz (or root) returns 200 with DBs reachable
└── e2e/
    └── test_login_smoke.py     # Playwright: open /login, log in, hit /dashboard, see expected element
```

Runtime budget:

- unit: < 5 s
- integration: < 30 s (single DB roundtrip per test, transaction rollback after each)
- e2e: < 2 min (one browser session, with --retries=2)

Total CI test job: ~3 min budget.

**Test DB — NEXORA_TEST**

Same SQL Server instance as `NEXORA_INT`, separate database named `NEXORA_TEST`. A dedicated SQL login (e.g. `nexora_test_user`) is created with rights scoped to `NEXORA_TEST` only — no SELECT/UPDATE/etc. on `NEXORA_INT`, `NEXORA_PROD`, or any other DB on the instance. This isolates tests from real data even if a connection string is mis-set. Tests own this DB; no other process writes to it.

Lifecycle on every CI run:

1. `scripts/test-db-reset.ps1` connects as DB owner, drops + recreates tables from `sql/test/schema.sql`, applies `sql/test/seed.sql`.
2. `schema.sql` is generated from `sql/accessManagement/` + `sql/config/tables/` — only the tables that round-1 tests reach. We do not mirror Statistics, Octo, or Generali schemas in round 1.
3. `seed.sql` inserts a known set of test users:
   - `admin@test.local` — bcrypt password `Test1234!`, granted `admin.view`, `admin.users.manage`, plus all permission codes from `pageVisability()` in `nx_lib/security.py`. 2FA secret pinned: `JBSWY3DPEHPK3PXP`.
   - `user@test.local` — bcrypt password `Test1234!`, granted only the default user permissions (whatever a freshly-created portal user gets in INT today). 2FA secret pinned: `KRSXG5CTMVRXEZLU`.
   - `noperm@test.local` — bcrypt password `Test1234!`, zero permissions. 2FA secret pinned: `MFRGGZDFMZTWQ2LK`.

   2FA secrets are pinned (committed in `sql/test/seed.sql`) so tests compute the current TOTP via `pyotp.TOTP(secret).now()`. These secrets only ever exist in NEXORA_TEST; they are not used by any real user.

Per-test isolation:

- Each integration test runs inside a SQLAlchemy transaction that is rolled back after the test. The seeded data is restored implicitly.
- For tests that genuinely need committed data (rare), they re-run the seed at the end via a fixture teardown.

Local dev DB:

- Each dev runs the same `test-db-reset.ps1` once against their local SQL Server to create the dev-local copy of `NEXORA_TEST`.
- The local pre-push hook does not reset the DB — it relies on transaction rollback for isolation. If a developer's local DB drifts, they re-run the reset script manually.

**`TEST.env` pattern**

`nx_lib/config.py` already loads `{ENVIRONMENT}.env` based on the `ENVIRONMENT` env var. Tests set `ENVIRONMENT=TEST` before importing `nx_lib`, so `TEST.env` controls all credentials.

`TEST.env` contents (uncommitted, lives next to `INT.env`/`PROD.env`):

```
ENVIRONMENT=TEST
FLASK_SECRET_KEY=<test-only key>
DB_SERVER_PRD=<server hosting NEXORA_TEST>
DB_UID=<test user>
DB_PWD=<test password>
DB_NEXORA=NEXORA_TEST
DB_STATISTICS=NEXORA_TEST          # placeholder — not hit by round-1 tests
DB_OCTO_RUNTIME=NEXORA_TEST        # placeholder
DB_GENERALI=NEXORA_TEST            # placeholder
GRAPH_TENANT_ID=test
GRAPH_CLIENT_ID=test
GRAPH_USERNAME=test@test.local
GRAPH_PASSWORD=test
GRAPH_CLIENT_SECRET=test
OCTO_CLIENT_SECRET=test
OCTO_CLIENT_ID=test
OCTO_GRANT_TYPE=client_credentials
OCTO_DOMAIN=https://test.invalid
BEXIO_PAT=test
```

`TEST.env.example` is committed at repo root with the same shape but no real values.

`nx_lib/config.py` does not change. The fact that Octo/Graph/Bexio credentials are fake doesn't matter — `SQLAlchemy.create_engine` is lazy, and Graph/Octo/Bexio calls are not made by round-1 routes.

**conftest.py — shared fixtures**

```python
import os
os.environ.setdefault("ENVIRONMENT", "TEST")  # MUST happen before importing nx_lib

import pytest
from nx_lib import create_app
from nx_lib.db import engineNexoraDB


@pytest.fixture(scope="session")
def app():
    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_conn():
    conn = engineNexoraDB.connect()
    trans = conn.begin()
    yield conn
    trans.rollback()
    conn.close()


@pytest.fixture()
def login(client):
    """Helper that logs in as one of the seeded test users."""
    def _login(user="user@test.local", password="Test1234!"):
        # 1. POST /login with creds
        # 2. POST /verify-2fa with pyotp.TOTP(secret).now()
        # ... returns the authenticated client
    return _login
```

**CI integration — `.github/workflows/deploy.yml` changes**

Restructure into two jobs:

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - name: Install Python deps
        shell: powershell
        run: D:\sydoc\tools\py\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
      - name: Install Playwright browsers
        shell: powershell
        run: D:\sydoc\tools\py\python.exe -m playwright install chromium
      - name: Reset NEXORA_TEST database
        shell: powershell
        run: .\scripts\test-db-reset.ps1
      - name: Run pytest
        shell: powershell
        env:
          ENVIRONMENT: TEST
        run: |
          D:\sydoc\tools\py\python.exe -m pytest tests `
            --junitxml=test-results/junit.xml `
            --html=test-results/report.html --self-contained-html `
            --reruns 2 --only-rerun "flaky_e2e" `
            -p no:cacheprovider `
            -o junit_logging=all
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: test-results/

  deploy:
    needs: test
    runs-on: self-hosted
    steps:
      # ...existing steps unchanged...
```

Key properties:

- `deploy` job has `needs: test`. If `test` job fails, `deploy` is skipped — IIS pool stays up running the previous version.
- Artifact upload uses `if: always()` so a failed run still surfaces the report.
- `TEST.env` is provisioned on the self-hosted runner once (outside CI) — same way `INT.env` / `PROD.env` are. Not in source.
- No environment file shuffling: tests run with `ENVIRONMENT=TEST` only inside the `test` job. The `deploy` job continues to use whatever `D:\sydoc\nexora\.env` already has (PROD).

**Local pre-push hook**

`scripts/install-hooks.ps1`:

- Writes a `.git/hooks/pre-push` file that invokes `pytest tests -q --reruns 2 --only-rerun flaky_e2e`
- Runs all three tiers — unit + integration + E2E — so the local gate matches CI exactly. Expected push time: ~3 min on a warm dev DB.
- One-time per clone: developer runs `.\scripts\install-hooks.ps1`
- Prerequisites the script checks for and fails fast on: `requirements-dev.txt` installed, `playwright install chromium` already run, `TEST.env` present, local NEXORA_TEST reachable.

`pre-push` content:

```bash
#!/usr/bin/env bash
# Auto-installed by scripts/install-hooks.ps1
exec python -m pytest tests -q --reruns 2 --only-rerun flaky_e2e
```

If a developer wants to push despite failures (rare, e.g. test-infra outage), they use `git push --no-verify` — and own the consequence if CI then blocks the deploy.

**Initial test inventory**

Unit (no Flask, no DB):

1. `test_has_permission_present` — fake `session={'permissions': ['admin.view']}`, assert `has_permission('admin.view') is True`
2. `test_has_permission_missing` — same fake session, assert `has_permission('admin.delete') is False`
3. `test_is_file_allowed_pdf` — `is_file_allowed("x.pdf", BytesIO(<pdf bytes>))` returns True
4. `test_is_file_allowed_mime_mismatch` — `is_file_allowed("x.pdf", BytesIO(b"<png bytes>"))` returns False (extension says pdf, libmagic says png)
5. `test_is_file_allowed_no_extension` — `is_file_allowed("x", ...)` returns False

Integration (Flask test client + NEXORA_TEST):

1. `test_login_page_renders` — `GET /login` returns 200 and contains login form
2. `test_login_valid_creds_and_2fa` — POST `/login` with `user@test.local` / valid TOTP → 302 to dashboard, session has `username`
3. `test_login_bad_password` — POST `/login` with wrong password → 401 / re-renders login with error
4. `test_protected_route_denies_unauthorised` — login as `noperm@test.local`, GET an admin-only route → 403

E2E (Playwright via `pytest-playwright` — Python, one test runner, one report, one gate):

1. `test_login_smoke` — launch browser, navigate to `http://localhost:8000/login`, fill creds for `user@test.local`, submit, enter TOTP (computed via `pyotp.TOTP(secret).now()` from the pinned seed secret), assert dashboard loads with the expected user-visible element (e.g. greeting text or nav item). Marked `@pytest.mark.flaky_e2e`. Backed by a session-scoped fixture that starts `nx_main.py` in a subprocess on port 8000 and waits for `/login` to respond.

**Failure policy**

Strict: any failing test in any tier blocks deploy. Specifically:

- pytest exits non-zero on any FAIL or ERROR → `test` job fails → `deploy` job is skipped (GitHub Actions default behavior for `needs:`)
- Skipped tests (`pytest.skip`) do not fail the job — use sparingly and only for legitimate "not applicable in this environment" cases
- E2E retries via `pytest-rerunfailures`: only tests marked `@pytest.mark.flaky_e2e` get `--reruns=2`. Unit and integration tests get zero retries — if they're flaky, fix them. After 2 reruns a still-failing E2E test fails the job.

If the test environment itself is broken (DB unreachable, runner offline) the job fails and deploy is blocked — by design. Fix the env, push a no-op commit (or re-run the workflow) to retry.

**Tooling — new files / changed files**

New files:

- `tests/__init__.py`
- `tests/conftest.py`
- `tests/unit/__init__.py`
- `tests/unit/test_security.py`
- `tests/unit/test_files.py`
- `tests/integration/__init__.py`
- `tests/integration/test_auth_flow.py`
- `tests/integration/test_permission_guard.py`
- `tests/e2e/__init__.py`
- `tests/e2e/test_login_smoke.py`
- `tests/e2e/conftest.py` — starts nx_main subprocess fixture
- `sql/test/schema.sql`
- `sql/test/seed.sql`
- `scripts/test-db-reset.ps1`
- `scripts/install-hooks.ps1`
- `pyproject.toml` (or `pytest.ini`) — pytest config: testpaths, junit, markers
- `requirements-dev.txt` — pytest, pytest-html, pytest-playwright, playwright, pyotp (already listed), pytest-flask (optional)
- `TEST.env.example`
- `docs/superpowers/specs/2026-05-12-test-gated-deploy-design.md` (this file)

Changed files:

- `.github/workflows/deploy.yml` — split into `test` + `deploy` jobs
- `.gitignore` — `test-results/` already excluded; add `TEST.env`, `htmlcov/`
- `README.md` — add a "Running tests" section

New deps in `requirements-dev.txt`:

```
pytest==8.3.4
pytest-html==4.1.1
pytest-playwright==0.5.2
pytest-rerunfailures==15.0
playwright==1.49.1
```

`pyodbc`, `pyotp`, `bcrypt`, `SQLAlchemy`, `Flask` already in `requirements.txt`. The Flask built-in test client is sufficient — no `pytest-flask` needed.

**SQL changes**

`sql/test/schema.sql` and `sql/test/seed.sql` are reference DDL. They are NOT appended to `environment_transfer_queries.tmp.sql` — that file is for INT/PROD changes. Per project convention they sit alongside `sql/accessManagement/` etc. as reference DDL applied manually to NEXORA_TEST.

If round 1 reveals that the runner's test DB user needs new grants on `master` to create databases, those grants go in `environment_transfer_queries.tmp.sql` with the standard header.

**Acceptance criteria**

1. `pytest tests` from a fresh clone (after running `pip install -r requirements-dev.txt`, `playwright install chromium`, `.\scripts\test-db-reset.ps1`) passes locally on Windows with `ENVIRONMENT=TEST`.
2. A push to a branch that breaks an existing test causes the `test` job to fail and the `deploy` job to be skipped (verify with an intentional failing test in a PR).
3. A push to `main` with all tests passing runs `test` → `deploy` and the deploy artifact (`test-results/`) is downloadable from the workflow run.
4. `.git/hooks/pre-push` (after running `install-hooks.ps1`) refuses pushes when local unit/integration tests fail.
5. `test-results/junit.xml` and `test-results/report.html` are produced on every CI run.

**Resolved decisions** (from user, 2026-05-12)

1. `NEXORA_TEST` lives on the same SQL Server instance as `NEXORA_INT`, in a separate DB, with a dedicated SQL login scoped to `NEXORA_TEST` only.
2. Playwright runs via `pytest-playwright` (Python). One runner, one report, one gate.
3. Local pre-push hook runs all three tiers (unit + integration + E2E) — matches CI exactly.

**Future work (next PRs after this one lands)**

- Coverage gate via `pytest-cov` — start at "report only", later enforce a minimum
- Integration tests against each view module (`admin`, `workitems`, `chat`, `invoices`, `notifications`, `dashboard`, `generali`, `profile`, `core`)
- Mock fixtures for Microsoft Graph, Octopus, Bexio
- Tests that exercise the other DB engines (`engineOctoDB`, `engineStatisticsDB`, `engineGeneraliDB`) — mocked or pointed at dedicated test DBs
- Pull-request CI: same `test` job runs on PRs to `main`, doesn't deploy
- Schedule a nightly job that runs the full suite against `NEXORA_INT` (read-only) as a regression canary

