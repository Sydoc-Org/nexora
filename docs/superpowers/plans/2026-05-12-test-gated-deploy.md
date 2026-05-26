# Test-gated deploy — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every deploy to PROD depend on passing tests. After this plan lands, `.github/workflows/deploy.yml` runs a `test` job first; if it fails, the `deploy` job is skipped. A local `pre-push` git hook runs the same suite.

**Architecture:** New `tests/` tree (unit + integration + e2e) using pytest. Tests run against a dedicated `NEXORA_TEST` SQL Server database with deterministic seed data. `TEST.env` (parallel to `INT.env`/`PROD.env`) drives all credentials via `ENVIRONMENT=TEST`. Playwright via `pytest-playwright`. CI splits into `test` + `deploy` jobs with `needs: test`.

**Tech Stack:** pytest 8.x, pytest-html, pytest-playwright, pytest-rerunfailures, playwright (chromium), pyodbc + SQL Server, Flask test client, GitHub Actions self-hosted runner.

**Spec:** `docs/superpowers/specs/2026-05-12-test-gated-deploy-design.md`

**Hard rules from CLAUDE.md (apply to every task below):**

- Never auto-commit. Every task ends with a "Stop here. Show user the diff" step; the user runs git operations.
- SQL Server changes that need to be applied to a real environment (INT, PROD) are appended to `environment_transfer_queries.tmp.sql` with a `--claudes new sql statement:` header. The user runs them manually.
- Browser-test changes yourself via Playwright. Don't ask the user to verify reachable UI behavior.

---

**Task 1: Add dev dependencies file**

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1.1: Create `requirements-dev.txt`**

Content of `requirements-dev.txt`:

```
# nexora — development / test dependencies.
# Install on top of requirements.txt:
#     pip install -r requirements-dev.txt
#
# Versions pinned to what the CI runner has been tested with.

# --- pytest core ---
pytest==8.3.4
pytest-html==4.1.1

# --- E2E (browser) ---
pytest-playwright==0.5.2
playwright==1.49.1

# --- retry policy for flaky E2E ---
pytest-rerunfailures==15.0
```

- [ ] **Step 1.2: Install dev deps locally to confirm versions resolve**

Run:

```powershell
.\venv\Scripts\pip install -r requirements-dev.txt
```

Expected: pip prints "Successfully installed ..." for the listed packages. If a version cannot resolve, replace with the latest patch in the same minor and re-run.

- [ ] **Step 1.3: Install Playwright chromium browser**

Run:

```powershell
.\venv\Scripts\python -m playwright install chromium
```

Expected: chromium downloads (~150 MB), prints "browser installed" or equivalent.

- [ ] **Step 1.4: Stop here. Show user the diff**

Output of:

```powershell
git status
git diff -- requirements-dev.txt
```

User reviews and commits.

---

**Task 2: Configure pytest**

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 2.1: Create `pyproject.toml`**

Content (just the test config — no build system, since nexora isn't a package):

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--tb=short",
    "--junitxml=test-results/junit.xml",
    "--html=test-results/report.html",
    "--self-contained-html",
]
markers = [
    "flaky_e2e: end-to-end browser tests that may be retried via pytest-rerunfailures",
]
filterwarnings = [
    "ignore::DeprecationWarning:flask_session.*",
    "ignore::DeprecationWarning:flask_limiter.*",
]
```

- [ ] **Step 2.2: Verify pytest discovers no tests yet (the dir doesn't exist) and exits cleanly**

Run:

```powershell
$env:ENVIRONMENT="TEST"
.\venv\Scripts\python -m pytest --collect-only
```

Expected: `ERROR: file or directory not found: tests` (because `tests/` doesn't exist yet) OR `no tests ran`. Both are acceptable for this step — we just want pytest to start up with our config and not error on the config itself.

If pytest complains about config (e.g. unknown option), fix the config file.

- [ ] **Step 2.3: Restore env var**

Run:

```powershell
Remove-Item Env:ENVIRONMENT
```

(Per CLAUDE.md memory: never leave `$env:X = "Y"` set without restoring.)

- [ ] **Step 2.4: Stop here. Show user the diff**

```powershell
git status
git diff -- pyproject.toml
```

User commits.

---

**Task 3: TEST.env.example and .gitignore updates**

**Files:**
- Create: `TEST.env.example`
- Modify: `.gitignore`

- [ ] **Step 3.1: Create `TEST.env.example`**

Content of `TEST.env.example`:

```
# Test environment configuration.
# Copy to TEST.env and fill in real values for your local test SQL Server.
# TEST.env is gitignored — never commit it.

ENVIRONMENT=TEST

# Flask
FLASK_SECRET_KEY=test-only-secret-not-used-in-prod

# SQL Server — same instance as NEXORA_INT, separate DB, separate login
DB_SERVER_PRD=<sql server hostname>
DB_UID=nexora_test_user
DB_PWD=<test password>
DB_NEXORA=NEXORA_TEST
DB_STATISTICS=NEXORA_TEST
DB_OCTO_RUNTIME=NEXORA_TEST
DB_GENERALI=NEXORA_TEST

# External services — fake values; round-1 tests don't invoke flows that hit them
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

- [ ] **Step 3.2: Append entries to `.gitignore`**

Add at the end of `.gitignore`:

```
# Test infra
TEST.env
htmlcov/
```

Note: `test-results/` and `docs/` are already excluded — do not add duplicate lines. Verify with:

```powershell
Select-String -Path .gitignore -Pattern '^test-results/'
Select-String -Path .gitignore -Pattern '^docs/'
```

Both must return one line each.

- [ ] **Step 3.3: Create local `TEST.env` for the developer's machine**

Copy `TEST.env.example` to `TEST.env` and fill in the local SQL Server credentials. This file is gitignored — it lives only on the developer's machine.

```powershell
Copy-Item TEST.env.example TEST.env
notepad TEST.env  # edit DB_SERVER_PRD, DB_PWD
```

The developer (or user) edits the real values. This step is not committable.

- [ ] **Step 3.4: Stop here. Show user the diff**

```powershell
git status
git diff -- .gitignore
```

`TEST.env.example` is a new tracked file. `TEST.env` is gitignored and should NOT appear in `git status`. User commits the example + gitignore changes.

---

**Task 4: SQL — NEXORA_TEST schema and seed**

**Files:**
- Create: `sql/test/schema.sql`
- Create: `sql/test/seed.sql`

The schema mirrors the subset of NEXORA tables that round-1 tests touch. Inspect `sql/accessManagement/` for the canonical DDL.

- [ ] **Step 4.1: Inspect existing access-management DDL to identify required tables**

Run:

```powershell
Get-ChildItem -Recurse sql/accessManagement | Where-Object { $_.Extension -eq '.sql' } | Select-Object FullName
```

For each file, read the contents and note: table names, columns, primary keys, FKs. The minimum set for round 1 is the tables that `dbo.spGetUserPermissions` reads from plus the `Users` table.

- [ ] **Step 4.2: Create `sql/test/schema.sql`**

Compose the DDL into one idempotent script. Pattern:

```sql
-- NEXORA_TEST schema. Idempotent — safe to run repeatedly.
-- Drops then recreates the test-relevant tables. Run via scripts/test-db-reset.ps1.

USE NEXORA_TEST;
GO

-- Drop in FK-safe order
IF OBJECT_ID('dbo.UserPermissions', 'U') IS NOT NULL DROP TABLE dbo.UserPermissions;
IF OBJECT_ID('dbo.Permissions', 'U') IS NOT NULL DROP TABLE dbo.Permissions;
IF OBJECT_ID('dbo.Users', 'U') IS NOT NULL DROP TABLE dbo.Users;
GO

-- Users table (subset of columns used by round-1 tests + auth flow)
CREATE TABLE dbo.Users (
    userid INT IDENTITY(1,1) PRIMARY KEY,
    username NVARCHAR(255) NOT NULL UNIQUE,
    passwordHash VARBINARY(255) NOT NULL,
    twoFactorSecret NVARCHAR(64) NULL,
    organizationcode NVARCHAR(50) NULL,
    locale NVARCHAR(10) NULL,
    -- ... add other NOT NULL columns from sql/accessManagement that nx_lib reads
);
GO

CREATE TABLE dbo.Permissions (
    permissionid INT IDENTITY(1,1) PRIMARY KEY,
    code NVARCHAR(100) NOT NULL UNIQUE
);
GO

CREATE TABLE dbo.UserPermissions (
    userid INT NOT NULL,
    permissionid INT NOT NULL,
    PRIMARY KEY (userid, permissionid),
    FOREIGN KEY (userid) REFERENCES dbo.Users(userid),
    FOREIGN KEY (permissionid) REFERENCES dbo.Permissions(permissionid)
);
GO

-- Stored proc that nx_lib/security.py calls
IF OBJECT_ID('dbo.spGetUserPermissions', 'P') IS NOT NULL DROP PROCEDURE dbo.spGetUserPermissions;
GO

CREATE PROCEDURE dbo.spGetUserPermissions @userid INT AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.code
    FROM dbo.UserPermissions up
    JOIN dbo.Permissions p ON p.permissionid = up.permissionid
    WHERE up.userid = @userid;
END;
GO
```

The exact column list MUST match what `nx_lib/views/auth.py` and `nx_lib/security.py` actually read. If you guess and miss a NOT NULL column, the seed insert fails. To be safe, inspect both files and add every column they touch.

- [ ] **Step 4.3: Create `sql/test/seed.sql`**

Content:

```sql
-- NEXORA_TEST seed data. Idempotent — safe to run after schema.sql.
-- Pinned passwords (Test1234!) hashed with bcrypt cost 12. Regenerate with:
--   python -c "import bcrypt; print(bcrypt.hashpw(b'Test1234!', bcrypt.gensalt(12)).decode())"

USE NEXORA_TEST;
GO

-- Wipe any prior seed
DELETE FROM dbo.UserPermissions;
DELETE FROM dbo.Users;
DELETE FROM dbo.Permissions;
DBCC CHECKIDENT('dbo.Users', RESEED, 0);
DBCC CHECKIDENT('dbo.Permissions', RESEED, 0);
GO

-- Permission codes used by round-1 tests
INSERT INTO dbo.Permissions (code) VALUES
    ('admin.view'),
    ('admin.users.manage'),
    ('dashboard.view');
GO

-- Test users. bcrypt hashes computed once and committed.
-- admin@test.local : password = Test1234!  : TOTP secret = JBSWY3DPEHPK3PXP
-- user@test.local  : password = Test1234!  : TOTP secret = KRSXG5CTMVRXEZLU
-- noperm@test.local: password = Test1234!  : TOTP secret = MFRGGZDFMZTWQ2LK

INSERT INTO dbo.Users (username, passwordHash, twoFactorSecret, organizationcode, locale) VALUES
    ('admin@test.local',  CAST('<bcrypt-hash-admin>'  AS VARBINARY(255)), 'JBSWY3DPEHPK3PXP', 'TEST', 'en'),
    ('user@test.local',   CAST('<bcrypt-hash-user>'   AS VARBINARY(255)), 'KRSXG5CTMVRXEZLU', 'TEST', 'en'),
    ('noperm@test.local', CAST('<bcrypt-hash-noperm>' AS VARBINARY(255)), 'MFRGGZDFMZTWQ2LK', 'TEST', 'en');
GO

-- Grant permissions
INSERT INTO dbo.UserPermissions (userid, permissionid)
SELECT u.userid, p.permissionid
FROM dbo.Users u, dbo.Permissions p
WHERE u.username = 'admin@test.local' AND p.code IN ('admin.view', 'admin.users.manage', 'dashboard.view');

INSERT INTO dbo.UserPermissions (userid, permissionid)
SELECT u.userid, p.permissionid
FROM dbo.Users u, dbo.Permissions p
WHERE u.username = 'user@test.local' AND p.code = 'dashboard.view';

-- noperm@test.local gets no permission rows
GO
```

- [ ] **Step 4.4: Generate the bcrypt hashes and paste them into seed.sql**

Run:

```powershell
.\venv\Scripts\python -c "import bcrypt; print(bcrypt.hashpw(b'Test1234!', bcrypt.gensalt(12)).decode())"
```

Run it three times (one per user — bcrypt salts each differently). Replace each `<bcrypt-hash-*>` placeholder in `seed.sql` with the resulting string (e.g. `$2b$12$abcdef...`).

If `nx_lib/views/auth.py` stores the bcrypt hash as bytes (the column is `VARBINARY`), the CAST in seed.sql converts the string to bytes — confirm by reading the login flow in `nx_lib/views/auth.py` to see exactly how the hash is compared. Adjust the column type or seed format if you find a mismatch.

- [ ] **Step 4.5: Stop here. Show user the diff**

```powershell
git status
git diff -- sql/test/
```

User commits.

---

**Task 5: Append NEXORA_TEST creation + grants to environment_transfer_queries.tmp.sql**

The DB and login must exist on the real SQL Server before any tests can run. Per project convention this goes through `environment_transfer_queries.tmp.sql` for the user to apply manually.

**Files:**
- Modify: `environment_transfer_queries.tmp.sql`

- [ ] **Step 5.1: Append the following block to `environment_transfer_queries.tmp.sql`**

```sql
--claudes new sql statement: create NEXORA_TEST database and scoped login for the test gate
USE master;
GO

IF DB_ID('NEXORA_TEST') IS NULL
BEGIN
    CREATE DATABASE NEXORA_TEST;
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = 'nexora_test_user')
BEGIN
    CREATE LOGIN nexora_test_user WITH PASSWORD = '<REPLACE_WITH_STRONG_PASSWORD>',
        CHECK_POLICY = ON, DEFAULT_DATABASE = NEXORA_TEST;
END
GO

USE NEXORA_TEST;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'nexora_test_user')
BEGIN
    CREATE USER nexora_test_user FOR LOGIN nexora_test_user;
END
GO

-- db_owner on NEXORA_TEST only; no rights anywhere else on the instance
ALTER ROLE db_owner ADD MEMBER nexora_test_user;
GO
```

- [ ] **Step 5.2: Tell the user this needs to run on INT and PROD test servers**

Output (as a chat message to the user, not a code change):

> Appended NEXORA_TEST creation + login to `environment_transfer_queries.tmp.sql`. Please run that block on the SQL Server instance, replacing `<REPLACE_WITH_STRONG_PASSWORD>` with the password you put in `TEST.env`. After that, run `scripts/test-db-reset.ps1` (created in Task 6) to load the schema and seed.

- [ ] **Step 5.3: Stop here. Show user the diff**

```powershell
git status
git diff -- environment_transfer_queries.tmp.sql
```

This file is itself gitignored (`*.tmp.sql` pattern in `.gitignore` — verify), so it won't appear in commits. User just runs the SQL on the server.

If `.gitignore` does NOT exclude `*.tmp.sql`, that's a project convention issue — flag to the user but do not auto-edit `.gitignore`.

---

**Task 6: Test-DB reset script**

**Files:**
- Create: `scripts/test-db-reset.ps1`

- [ ] **Step 6.1: Create `scripts/test-db-reset.ps1`**

Content:

```powershell
<#
.SYNOPSIS
    Resets NEXORA_TEST to a known state: applies sql/test/schema.sql then sql/test/seed.sql.

.DESCRIPTION
    Reads connection info from TEST.env at the repo root. Uses sqlcmd.
    Idempotent: safe to run any number of times. Run this:
      - Once after creating NEXORA_TEST via environment_transfer_queries.tmp.sql
      - In CI before every test run
      - Locally whenever the test DB has drifted

.EXAMPLE
    .\scripts\test-db-reset.ps1
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$testEnv = Join-Path $repoRoot 'TEST.env'
if (-not (Test-Path $testEnv)) {
    throw "TEST.env not found at $testEnv. Copy TEST.env.example and fill in values."
}

# Parse KEY=VALUE lines
$env_vars = @{}
Get-Content $testEnv | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $k, $v = $line -split '=', 2
        $env_vars[$k.Trim()] = $v.Trim()
    }
}

$server = $env_vars['DB_SERVER_PRD']
$uid = $env_vars['DB_UID']
$pwd = $env_vars['DB_PWD']
$db = $env_vars['DB_NEXORA']

if (-not $server -or -not $uid -or -not $pwd -or -not $db) {
    throw "TEST.env is missing one of: DB_SERVER_PRD, DB_UID, DB_PWD, DB_NEXORA"
}

if ($db -ne 'NEXORA_TEST') {
    throw "Refusing to run: DB_NEXORA in TEST.env must be 'NEXORA_TEST', got '$db'."
}

$schema = Join-Path $repoRoot 'sql\test\schema.sql'
$seed = Join-Path $repoRoot 'sql\test\seed.sql'

Write-Host "Applying schema to $db on $server..."
sqlcmd -S $server -U $uid -P $pwd -d $db -i $schema -b
if ($LASTEXITCODE -ne 0) { throw "schema.sql failed (exit $LASTEXITCODE)" }

Write-Host "Applying seed to $db on $server..."
sqlcmd -S $server -U $uid -P $pwd -d $db -i $seed -b
if ($LASTEXITCODE -ne 0) { throw "seed.sql failed (exit $LASTEXITCODE)" }

Write-Host "NEXORA_TEST reset complete."
```

- [ ] **Step 6.2: Run the reset script to confirm it works**

```powershell
.\scripts\test-db-reset.ps1
```

Expected: prints "Applying schema...", "Applying seed...", "NEXORA_TEST reset complete." Exits with code 0.

If `sqlcmd` is not on PATH, install SQL Server command-line tools or use the full path. Note the path used in a comment in the script if non-default.

If the script fails because the bcrypt hashes in `seed.sql` aren't valid bcrypt strings, redo Step 4.4.

- [ ] **Step 6.3: Stop here. Show user the diff**

```powershell
git status
git diff -- scripts/test-db-reset.ps1
```

User commits.

---

**Task 7: Tests root with shared fixtures**

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 7.1: Create `tests/__init__.py`**

Content: empty file.

- [ ] **Step 7.2: Create `tests/conftest.py`**

Content:

```python
"""Shared pytest fixtures for the nexora test suite.

This file must set ENVIRONMENT=TEST before any nx_lib import, otherwise
nx_lib.config would load whatever environment is currently active.
"""

import os

# CRITICAL: set BEFORE importing nx_lib. setdefault avoids overwriting if a
# caller deliberately set a different environment (e.g. for debug).
os.environ.setdefault("ENVIRONMENT", "TEST")

import pytest  # noqa: E402
import pyotp  # noqa: E402
from sqlalchemy import text  # noqa: E402

from nx_lib import create_app  # noqa: E402
from nx_lib.db import engineNexoraDB  # noqa: E402


# Pinned TOTP secrets — must match sql/test/seed.sql exactly.
TOTP_SECRETS = {
    "admin@test.local": "JBSWY3DPEHPK3PXP",
    "user@test.local": "KRSXG5CTMVRXEZLU",
    "noperm@test.local": "MFRGGZDFMZTWQ2LK",
}

TEST_PASSWORD = "Test1234!"


@pytest.fixture(scope="session")
def app():
    """Flask app configured for testing. One per test session."""
    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,  # CSRF gets in the way of POSTing from the test client
    )
    yield flask_app


@pytest.fixture()
def client(app):
    """Flask test client. Fresh per test."""
    return app.test_client()


@pytest.fixture()
def db_conn():
    """SQLAlchemy connection with transaction-scoped isolation.

    Anything written through this connection is rolled back at end-of-test,
    so tests can mutate freely without polluting other tests.
    """
    conn = engineNexoraDB.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


@pytest.fixture()
def totp_for():
    """Compute the current TOTP code for a seeded test user."""
    def _totp(username):
        secret = TOTP_SECRETS[username]
        return pyotp.TOTP(secret).now()
    return _totp


@pytest.fixture()
def login(client, totp_for):
    """Log in as a seeded test user. Returns the authenticated test client.

    Exact endpoint paths depend on nx_lib/views/auth.py — the implementor of
    Task 13 confirms /login and /verify-2fa (or whatever they are named) and
    fills in this fixture body.
    """
    def _login(username="user@test.local", password=TEST_PASSWORD):
        resp = client.post("/login", data={"username": username, "password": password})
        # If /login returns 200 with a 2FA form, post the code:
        if resp.status_code == 200 and b"2FA" in resp.data:
            code = totp_for(username)
            resp = client.post("/verify-2fa", data={"code": code})
        assert resp.status_code in (200, 302), f"login failed: {resp.status_code} {resp.data[:200]!r}"
        return client
    return _login
```

- [ ] **Step 7.3: Verify pytest collects (no tests yet, but conftest must import cleanly)**

```powershell
.\venv\Scripts\python -m pytest --collect-only
```

Expected: `no tests collected` and exit code 5 (pytest's "no tests" code), OR exit 0 with empty collection. NOT an import error.

If you see `ImportError` for `nx_lib`, your repo root isn't on `sys.path` — that's actually fine because pytest adds `tests/`'s parent to `sys.path` automatically (since `pyproject.toml`'s `testpaths` is `["tests"]`). If it still fails, add a `[tool.pytest.ini_options] pythonpath = ["."]` line to `pyproject.toml`.

- [ ] **Step 7.4: Stop here. Show user the diff**

```powershell
git status
git diff -- tests/
```

User commits.

---

**Task 8: First unit test — `has_permission` returns True when permission present**

**Files:**
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_security.py`

- [ ] **Step 8.1: Create `tests/unit/__init__.py`**

Content: empty file.

- [ ] **Step 8.2: Write the first test**

Create `tests/unit/test_security.py`:

```python
"""Unit tests for nx_lib.security — pure logic, no DB."""

from unittest.mock import patch

from nx_lib.security import has_permission


def test_has_permission_returns_true_when_present():
    with patch("nx_lib.security.session", {"permissions": ["admin.view"]}):
        assert has_permission("admin.view") is True
```

- [ ] **Step 8.3: Run the test**

```powershell
.\venv\Scripts\python -m pytest tests/unit/test_security.py -v
```

Expected: 1 passed.

If it fails, read the error: most likely `has_permission` uses `session.get("permissions", [])` and our patch needs to be a dict that supports `.get()`. A plain `dict` does. If the failure says "AttributeError: 'dict' object has no attribute 'get'" — that's not a real error; investigate.

- [ ] **Step 8.4: Confirm the test catches a regression**

Temporarily edit `nx_lib/security.py` line ~33-35:

```python
def has_permission(code: str) -> bool:
    return False  # deliberately broken
```

Run:

```powershell
.\venv\Scripts\python -m pytest tests/unit/test_security.py -v
```

Expected: FAIL. The test asserts `is True`, the function returns `False`.

- [ ] **Step 8.5: Revert `nx_lib/security.py` to its original state**

```powershell
git checkout nx_lib/security.py
```

Run the test again:

```powershell
.\venv\Scripts\python -m pytest tests/unit/test_security.py -v
```

Expected: 1 passed.

- [ ] **Step 8.6: Stop here. Show user the diff**

```powershell
git status
git diff -- tests/
```

User commits.

---

**Task 9: Second unit test — `has_permission` returns False when missing**

**Files:**
- Modify: `tests/unit/test_security.py`

- [ ] **Step 9.1: Append the second test**

Add to `tests/unit/test_security.py`:

```python
def test_has_permission_returns_false_when_missing():
    with patch("nx_lib.security.session", {"permissions": ["dashboard.view"]}):
        assert has_permission("admin.delete") is False


def test_has_permission_returns_false_when_no_permissions_in_session():
    with patch("nx_lib.security.session", {}):
        assert has_permission("admin.view") is False
```

- [ ] **Step 9.2: Run all unit tests**

```powershell
.\venv\Scripts\python -m pytest tests/unit -v
```

Expected: 3 passed.

- [ ] **Step 9.3: Stop here. Show user the diff**

```powershell
git status
git diff -- tests/unit/test_security.py
```

User commits.

---

**Task 10: Unit tests for `is_file_allowed`**

**Files:**
- Create: `tests/unit/test_files.py`

- [ ] **Step 10.1: Write the file unit tests**

Create `tests/unit/test_files.py`:

```python
"""Unit tests for nx_lib.files — MIME sniffing via libmagic."""

from io import BytesIO

from nx_lib.files import is_file_allowed


# Tiny but valid PDF (1.4) — accepted by libmagic as application/pdf
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF\n"

# 1x1 transparent PNG
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_is_file_allowed_pdf():
    assert is_file_allowed("invoice.pdf", BytesIO(PDF_BYTES)) is True


def test_is_file_allowed_png():
    assert is_file_allowed("photo.png", BytesIO(PNG_BYTES)) is True


def test_is_file_allowed_extension_mismatch():
    """Extension says PDF, libmagic detects PNG — rejected."""
    assert is_file_allowed("evil.pdf", BytesIO(PNG_BYTES)) is False


def test_is_file_allowed_no_extension():
    assert is_file_allowed("noextension", BytesIO(PDF_BYTES)) is False


def test_is_file_allowed_unknown_extension():
    assert is_file_allowed("script.exe", BytesIO(b"MZ\x90\x00")) is False
```

- [ ] **Step 10.2: Run the file tests**

```powershell
.\venv\Scripts\python -m pytest tests/unit/test_files.py -v
```

Expected: 5 passed.

If `python-magic-bin` is not installed on the dev machine, install it (it's already in `requirements.txt`). If the PDF byte sequence is not detected as `application/pdf` by libmagic on Windows (some libmagic builds want a longer PDF stream), replace `PDF_BYTES` with a real 2-3 KB PDF file's bytes — read from a fixture file under `tests/unit/fixtures/`.

- [ ] **Step 10.3: Run the whole unit suite**

```powershell
.\venv\Scripts\python -m pytest tests/unit -v
```

Expected: 8 passed (3 from security + 5 from files).

- [ ] **Step 10.4: Stop here. Show user the diff**

```powershell
git status
git diff -- tests/unit/test_files.py
```

User commits.

---

**Task 11: Integration test scaffold — login page renders**

Before this task: confirm exact route paths in `nx_lib/views/auth.py`. The fixture in `conftest.py` assumes `/login` and `/verify-2fa`. If different, update `conftest.py` and adjust the tests below.

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_auth_flow.py`

- [ ] **Step 11.1: Inspect `nx_lib/views/auth.py` for actual paths**

Run:

```powershell
Select-String -Path nx_lib/views/auth.py -Pattern 'add_url_rule|@.*\.route'
```

Note every URL rule. The test below uses `/login`. If the actual path is different (e.g. `/auth/login`), use that.

- [ ] **Step 11.2: Create `tests/integration/__init__.py`**

Content: empty file.

- [ ] **Step 11.3: Write the login-page-renders test**

Create `tests/integration/test_auth_flow.py`:

```python
"""Integration tests for the auth flow — Flask test client against NEXORA_TEST."""


def test_login_page_renders(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    # Sanity-check: the response body contains a form
    assert b"<form" in resp.data.lower()
```

- [ ] **Step 11.4: Run the test**

```powershell
.\venv\Scripts\python -m pytest tests/integration/test_auth_flow.py::test_login_page_renders -v
```

Expected: 1 passed.

If it fails with `404`, your route path is wrong — fix the URL in the test. If it fails with `500`, the app crashed on startup — read the traceback. The most likely cause is a `nx_lib` import side-effect that doesn't tolerate `TEST.env` placeholder values; address by either patching the offending module or filling in a real value in `TEST.env`.

- [ ] **Step 11.5: Stop here. Show user the diff**

```powershell
git status
git diff -- tests/integration/test_auth_flow.py
```

User commits.

---

**Task 12: Integration test — login with valid creds + 2FA**

**Files:**
- Modify: `tests/integration/test_auth_flow.py`

- [ ] **Step 12.1: Append the valid-login test**

Add to `tests/integration/test_auth_flow.py`:

```python
def test_login_valid_creds_and_2fa(client, totp_for):
    # Step 1: post creds
    resp = client.post(
        "/login",
        data={"username": "user@test.local", "password": "Test1234!"},
        follow_redirects=False,
    )
    # Either:
    #   200 + 2FA form (most likely) — proceed to 2FA submission
    #   302 — already logged in (no 2FA configured for this user, shouldn't happen here)
    assert resp.status_code in (200, 302)

    if resp.status_code == 200:
        code = totp_for("user@test.local")
        resp = client.post("/verify-2fa", data={"code": code}, follow_redirects=False)
        assert resp.status_code == 302, f"2FA submit failed: {resp.data[:200]!r}"

    # Session cookie should now be set
    with client.session_transaction() as sess:
        assert sess.get("username") == "user@test.local"
```

- [ ] **Step 12.2: Run it**

```powershell
.\venv\Scripts\python -m pytest tests/integration/test_auth_flow.py::test_login_valid_creds_and_2fa -v
```

Expected: 1 passed.

If the actual auth flow uses different field names (`email` instead of `username`, `otp` instead of `code`), inspect `templates/login.html` and `nx_lib/views/auth.py` and adjust the test accordingly. If it uses a different 2FA endpoint, adjust both the test and `conftest.py`'s `login` fixture in lockstep.

- [ ] **Step 12.3: Stop here. Show user the diff**

User commits.

---

**Task 13: Integration test — bad password**

**Files:**
- Modify: `tests/integration/test_auth_flow.py`

- [ ] **Step 13.1: Append the bad-password test**

Add to `tests/integration/test_auth_flow.py`:

```python
def test_login_bad_password_rejected(client):
    resp = client.post(
        "/login",
        data={"username": "user@test.local", "password": "wrong-password"},
        follow_redirects=False,
    )
    # Auth flow should reject — either re-render login (200) with an error,
    # or return 401. Both indicate "not authenticated."
    assert resp.status_code in (200, 401)

    with client.session_transaction() as sess:
        assert "username" not in sess


def test_login_unknown_user_rejected(client):
    resp = client.post(
        "/login",
        data={"username": "nobody@nowhere.local", "password": "anything"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 401)

    with client.session_transaction() as sess:
        assert "username" not in sess
```

- [ ] **Step 13.2: Run both new tests**

```powershell
.\venv\Scripts\python -m pytest tests/integration/test_auth_flow.py -v
```

Expected: 4 passed.

- [ ] **Step 13.3: Stop here. Show user the diff**

User commits.

---

**Task 14: Integration test — permission guard denies unauthorised user**

**Files:**
- Create: `tests/integration/test_permission_guard.py`

- [ ] **Step 14.1: Confirm the protected route**

The plan uses `/admin`, which is the admin dashboard guarded by `@require_permission("admin.view")` at `nx_lib/views/admin.py:35-36`. Both the route and the permission code are already covered by the seed (Task 4.3): `admin@test.local` has `admin.view`, `noperm@test.local` has nothing.

- [ ] **Step 14.2: Write the test**

Create `tests/integration/test_permission_guard.py`:

```python
"""Integration tests verifying that @require_permission denies unauthorised users."""

ADMIN_ROUTE = "/admin"  # guarded by @require_permission("admin.view") in nx_lib/views/admin.py


def test_protected_route_denies_noperm_user(login):
    client = login(username="noperm@test.local")
    resp = client.get(ADMIN_ROUTE)
    assert resp.status_code == 403, f"expected 403, got {resp.status_code}"


def test_protected_route_allows_admin_user(login):
    client = login(username="admin@test.local")
    resp = client.get(ADMIN_ROUTE)
    # 200 if route renders normally; 302 if the view itself redirects (e.g. to a sub-page).
    # 403 would mean the admin seed is missing admin.view.
    assert resp.status_code in (200, 302), f"admin denied: {resp.status_code}"
```

- [ ] **Step 14.3: Run both tests**

```powershell
.\venv\Scripts\python -m pytest tests/integration/test_permission_guard.py -v
```

Expected: 2 passed.

If `test_protected_route_allows_admin_user` fails with 403, the seed grant in Task 4.3 is missing a permission — add it to `seed.sql` and re-run `scripts/test-db-reset.ps1`. If `test_protected_route_denies_noperm_user` fails with 200, the route isn't actually permission-guarded — pick a different route.

- [ ] **Step 14.4: Run the full integration suite**

```powershell
.\venv\Scripts\python -m pytest tests/integration -v
```

Expected: 6 passed.

- [ ] **Step 14.5: Stop here. Show user the diff**

User commits.

---

**Task 15: E2E — subprocess fixture for nx_main + Playwright login smoke**

**Files:**
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_login_smoke.py`

- [ ] **Step 15.1: Create `tests/e2e/__init__.py`**

Content: empty file.

- [ ] **Step 15.2: Create `tests/e2e/conftest.py` with subprocess + wait-for-ready**

Content:

```python
"""E2E test fixtures. Starts nx_main.py in a subprocess so Playwright can drive
a real browser against a real Flask server."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

import pytest


E2E_PORT = 8765
E2E_BASE_URL = f"http://localhost:{E2E_PORT}"


def _port_is_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_http(url, timeout_s=30):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except URLError:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def nexora_server():
    """Start nx_main on E2E_PORT for the duration of the test session."""
    if _port_is_open(E2E_PORT):
        raise RuntimeError(
            f"Port {E2E_PORT} already in use. Stop the other process or change E2E_PORT."
        )

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["ENVIRONMENT"] = "TEST"
    env["FLASK_RUN_PORT"] = str(E2E_PORT)

    # nx_main runs app.run(host='0.0.0.0', port=8000) by default. We override port
    # via the env var below; nx_main reads it if present (verify in nx_main.py —
    # if it doesn't, switch to `flask run --port 8765` invocation).
    proc = subprocess.Popen(
        [sys.executable, "nx_main.py"],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        if not _wait_for_http(f"{E2E_BASE_URL}/login", timeout_s=30):
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            proc.terminate()
            proc.wait(timeout=5)
            raise RuntimeError(f"nx_main did not become reachable in 30s. Output:\n{out}")
        yield E2E_BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
```

If `nx_main.py` hardcodes port 8000 and ignores `FLASK_RUN_PORT`, modify `nx_main.py` to read the env var:

```python
if __name__ == "__main__":
    port = int(os.environ.get("FLASK_RUN_PORT", "8000"))
    app.run(host='0.0.0.0', port=port)
```

That's a tiny non-invasive change.

- [ ] **Step 15.3: Create the smoke test**

Create `tests/e2e/test_login_smoke.py`:

```python
"""Playwright smoke test — full login + 2FA + dashboard."""

import pyotp
import pytest


@pytest.mark.flaky_e2e
def test_login_smoke(nexora_server, page):
    page.goto(f"{nexora_server}/login")

    page.fill('input[name="username"]', "user@test.local")
    page.fill('input[name="password"]', "Test1234!")
    page.click('button[type="submit"]')

    # If the app routes through a 2FA page after login:
    if page.locator('input[name="code"]').is_visible(timeout=5000):
        code = pyotp.TOTP("KRSXG5CTMVRXEZLU").now()
        page.fill('input[name="code"]', code)
        page.click('button[type="submit"]')

    # After auth, we expect to land on the dashboard. Update this selector to
    # something that uniquely identifies the dashboard in templates/dashboard.html
    # (or wherever the default landing page lives for a 'user' role).
    page.wait_for_url("**/dashboard", timeout=10000)
    assert "/dashboard" in page.url
```

The form field names (`username`, `password`, `code`) and the dashboard URL pattern are the actual values from `templates/login.html` and the dashboard route. Inspect those templates and routes in this task and adjust if they differ.

- [ ] **Step 15.4: Run the E2E test**

```powershell
.\venv\Scripts\python -m pytest tests/e2e -v --reruns 2 --only-rerun flaky_e2e
```

Expected: 1 passed (possibly after 1-2 retries on a slow first launch).

Common failure modes:
- Selector mismatch: open `templates/login.html`, copy the actual input names.
- Subprocess startup race: increase `_wait_for_http` timeout.
- Port collision: change `E2E_PORT`.
- 2FA mismatch: TOTP secret must equal what's in `seed.sql`. Re-check Task 4.3.

- [ ] **Step 15.5: Run the entire test suite end-to-end**

```powershell
.\venv\Scripts\python -m pytest tests -v --reruns 2 --only-rerun flaky_e2e
```

Expected: all tests passed. Total: 8 unit + 6 integration + 1 e2e = 15 tests.

The `test-results/` directory now contains `junit.xml` and `report.html`.

- [ ] **Step 15.6: Stop here. Show user the diff**

User commits.

---

**Task 16: Local pre-push hook installer**

**Files:**
- Create: `scripts/install-hooks.ps1`

- [ ] **Step 16.1: Create the installer**

Content of `scripts/install-hooks.ps1`:

```powershell
<#
.SYNOPSIS
    Installs the nexora pre-push hook into .git/hooks.

.DESCRIPTION
    Run once per clone. The hook runs the full pytest suite (unit + integration + e2e)
    before allowing `git push`. If tests fail, the push is aborted.

    Bypass for emergencies: `git push --no-verify`.

.EXAMPLE
    .\scripts\install-hooks.ps1
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$hookPath = Join-Path $repoRoot '.git\hooks\pre-push'

if (-not (Test-Path (Join-Path $repoRoot '.git'))) {
    throw "Not a git repo (no .git directory at $repoRoot)"
}

# Sanity checks
$checks = @(
    @{ Path = (Join-Path $repoRoot 'TEST.env'); Msg = "TEST.env missing. Copy TEST.env.example and fill in values." },
    @{ Path = (Join-Path $repoRoot 'venv'); Msg = "venv missing. Create with: python -m venv venv && .\venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt" },
    @{ Path = (Join-Path $repoRoot 'tests'); Msg = "tests/ missing — nothing to run." }
)
foreach ($c in $checks) {
    if (-not (Test-Path $c.Path)) { throw $c.Msg }
}

$hookContent = @'
#!/usr/bin/env bash
# Auto-installed by scripts/install-hooks.ps1.
# Runs the full nexora test suite before allowing push.
# Bypass with: git push --no-verify
set -e
echo "[pre-push] Running pytest..."
exec ./venv/Scripts/python -m pytest tests -q --reruns 2 --only-rerun flaky_e2e
'@

Set-Content -Path $hookPath -Value $hookContent -Encoding UTF8 -NoNewline

# Git on Windows needs the hook to be executable. Setting +x is a no-op on NTFS,
# but Git for Windows interprets the bash shebang anyway.
Write-Host "Installed pre-push hook at $hookPath"
Write-Host "Test it with: git push --dry-run"
```

- [ ] **Step 16.2: Run the installer**

```powershell
.\scripts\install-hooks.ps1
```

Expected: prints "Installed pre-push hook at ..." with no error.

- [ ] **Step 16.3: Verify the hook fires on push attempt**

```powershell
git push --dry-run
```

Expected: pytest runs, suite passes, dry-run completes. If tests fail, the push is aborted.

Don't actually push — this is just verification.

- [ ] **Step 16.4: Stop here. Show user the diff**

User commits.

---

**Task 17: Update `.github/workflows/deploy.yml` — split into `test` + `deploy`**

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 17.1: Read the current workflow to recall the exact deploy steps**

```powershell
Get-Content .github\workflows\deploy.yml
```

The deploy job's steps (verify env, stop pool, sync, start pool) are unchanged — they only move under `jobs.deploy` and gain `needs: test`.

- [ ] **Step 17.2: Rewrite `.github/workflows/deploy.yml`**

Replace the entire file with:

```yaml
name: Deploy
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4

      - name: Install Python deps
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          D:\sydoc\tools\py\python.exe -m pip install --quiet -r requirements.txt
          D:\sydoc\tools\py\python.exe -m pip install --quiet -r requirements-dev.txt

      - name: Install Playwright chromium
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          D:\sydoc\tools\py\python.exe -m playwright install chromium

      - name: Verify TEST.env exists on runner
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          $testEnv = "${{ github.workspace }}\TEST.env"
          if (-not (Test-Path $testEnv)) {
            throw "Aborting tests: $testEnv not found. Provision TEST.env on the runner."
          }
          $envLine = Get-Content $testEnv | Where-Object { $_ -match '^\s*ENVIRONMENT\s*=' } | Select-Object -First 1
          if ($envLine -notmatch '^\s*ENVIRONMENT\s*=\s*"?TEST"?\s*$') {
            throw "TEST.env must contain 'ENVIRONMENT=TEST'. Found: '$envLine'"
          }

      - name: Reset NEXORA_TEST database
        shell: powershell
        run: .\scripts\test-db-reset.ps1

      - name: Run pytest
        shell: powershell
        env:
          ENVIRONMENT: TEST
        run: |
          $ErrorActionPreference = 'Stop'
          D:\sydoc\tools\py\python.exe -m pytest tests `
            --reruns 2 --only-rerun flaky_e2e `
            -p no:cacheprovider `
            -o junit_logging=all

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: test-results/
          if-no-files-found: warn

  deploy:
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4

      - name: Verify prod env files
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          $deployDir = "D:\sydoc\nexora"
          $envFile = "$deployDir\.env"
          $prodEnvFile = "$deployDir\PROD.env"

          if (-not (Test-Path $envFile)) {
            throw "Aborting deploy: $envFile not found."
          }
          $envLine = Get-Content $envFile | Where-Object { $_ -match '^\s*ENVIRONMENT\s*=' } | Select-Object -First 1
          if ($envLine -notmatch '^\s*ENVIRONMENT\s*=\s*"?PROD"?\s*$') {
            throw "Aborting deploy: $envFile must contain 'ENVIRONMENT=PROD'. Found: '$envLine'"
          }
          Write-Host "Verified: $envFile has ENVIRONMENT=PROD"

          if (-not (Test-Path $prodEnvFile)) {
            throw "Aborting deploy: $prodEnvFile not found. The app will fail to load secrets without it."
          }
          Write-Host "Verified: $prodEnvFile exists"

      - name: Stop app pool and service
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          Import-Module WebAdministration

          $pool = "DefaultAppPool"
          Write-Host "App pool '$pool' initial state: $((Get-WebAppPoolState -Name $pool).Value)"

          $deadline = (Get-Date).AddSeconds(60)
          while ((Get-WebAppPoolState -Name $pool).Value -in @('Starting','Stopping')) {
            if ((Get-Date) -gt $deadline) {
              throw "App pool '$pool' stuck in transition: $((Get-WebAppPoolState -Name $pool).Value)"
            }
            Start-Sleep -Seconds 2
          }

          if ((Get-WebAppPoolState -Name $pool).Value -eq 'Started') {
            Stop-WebAppPool -Name $pool
          }

          $deadline = (Get-Date).AddSeconds(120)
          while ((Get-WebAppPoolState -Name $pool).Value -ne 'Stopped') {
            if ((Get-Date) -gt $deadline) {
              throw "App pool '$pool' did not stop within 120s (state: $((Get-WebAppPoolState -Name $pool).Value))"
            }
            Start-Sleep -Seconds 2
          }
          Write-Host "App pool '$pool' is Stopped."

          $svc = Get-Service -Name 'ngrok' -ErrorAction SilentlyContinue
          if ($svc -and $svc.Status -ne 'Stopped') {
            Stop-Service -Name 'ngrok' -Force
            $svc.WaitForStatus('Stopped', '00:01:00')
          }
          Write-Host "Service 'ngrok' is Stopped."

      - name: Sync to deploy folder
        shell: powershell
        run: |
          robocopy "${{ github.workspace }}" "D:\sydoc\nexora" /MIR /R:3 /W:2 `
            /XD .git .github .claude .playwright-mcp .superpowers .vscode .idea __pycache__ session logs uploads screenshots scripts export-help news sql tests test-results `
            /XF *.env ngrok.yaml .gitignore CLAUDE.md nx.ps1 babel.cfg messages.pot environment_transfer_queries.tmp.sql howtobabel.txt howtoiis.txt howtongrok.txt requirements.txt requirements-dev.txt README.md pyproject.toml
          if ($LASTEXITCODE -lt 8) { exit 0 } else { exit $LASTEXITCODE }

      - name: Start app pool and service
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          Import-Module WebAdministration

          $pool = "DefaultAppPool"
          $deadline = (Get-Date).AddSeconds(60)
          while ((Get-WebAppPoolState -Name $pool).Value -in @('Starting','Stopping')) {
            if ((Get-Date) -gt $deadline) {
              throw "App pool '$pool' stuck in transition: $((Get-WebAppPoolState -Name $pool).Value)"
            }
            Start-Sleep -Seconds 2
          }

          if ((Get-WebAppPoolState -Name $pool).Value -eq 'Stopped') {
            Start-WebAppPool -Name $pool
          }

          $deadline = (Get-Date).AddSeconds(60)
          while ((Get-WebAppPoolState -Name $pool).Value -ne 'Started') {
            if ((Get-Date) -gt $deadline) {
              throw "App pool '$pool' did not start within 60s (state: $((Get-WebAppPoolState -Name $pool).Value))"
            }
            Start-Sleep -Seconds 2
          }
          Write-Host "App pool '$pool' is Started."

          Start-Service -Name 'ngrok'
          (Get-Service -Name 'ngrok').WaitForStatus('Running', '00:01:00')
          Write-Host "Service 'ngrok' is Running."
```

Key differences from the original:

- Trigger now includes `pull_request: branches: [main]` so the `test` job runs on PRs too. This lets the gate be verified on a PR before merging.
- New `test` job with checkout, deps install, Playwright install, TEST.env verify, DB reset, pytest, artifact upload. Runs on both `push` and `pull_request`.
- `deploy` job has `needs: test` AND `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` — it runs ONLY on push-to-main, never on PRs. So PRs prove the gate works without ever risking a real deploy.
- `robocopy` `/XD` list adds `tests test-results` (don't ship test artifacts to prod).
- `robocopy` `/XF` list adds `requirements-dev.txt pyproject.toml` (also not needed in prod).

- [ ] **Step 17.2.1: One-time runner provisioning checklist (do, then check off)**

These are runner-side steps the user runs on the self-hosted runner machine, NOT in code:

- [ ] Copy `TEST.env.example` from a fresh clone of the repo to the workspace and fill in real test SQL Server credentials, save as `TEST.env`. The workspace is at `${{ github.workspace }}` per run — provision the file in a way that survives `actions/checkout@v4` (e.g. add it to `.gitignore`-safe location and have `actions/checkout` not clean it, OR have a runner-level pre-step that copies it from a secrets location).
- [ ] Run `environment_transfer_queries.tmp.sql` on the SQL Server to create `NEXORA_TEST` + login.
- [ ] On the runner, run `D:\sydoc\tools\py\python.exe -m pip install -r requirements-dev.txt` and `D:\sydoc\tools\py\python.exe -m playwright install chromium` once (the workflow re-runs these but the first install is the slow one).

Easiest path for the TEST.env-on-runner concern: place `TEST.env` at a known runner-local path outside the workspace (e.g. `C:\sydoc\runner-secrets\TEST.env`) and add a workflow step that copies it into `${{ github.workspace }}` before the verify step. If you go that route, add this step BEFORE the "Verify TEST.env exists" step:

```yaml
      - name: Copy TEST.env into workspace
        shell: powershell
        run: |
          Copy-Item C:\sydoc\runner-secrets\TEST.env "${{ github.workspace }}\TEST.env" -Force
```

- [ ] **Step 17.3: Verify the YAML parses**

```powershell
D:\sydoc\tools\py\python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"
```

Expected: exits 0, no output. If you get a YAML parse error, fix the indent.

- [ ] **Step 17.4: Stop here. Show user the diff**

```powershell
git status
git diff -- .github/workflows/deploy.yml
```

User commits.

---

**Task 18: README — running tests**

**Files:**
- Modify: `README.md`

- [ ] **Step 18.1: Append a Tests section**

Add to the end of `README.md` (or replace an existing Tests section if any):

```markdown
## Running tests

Tests live in `tests/` (`unit/`, `integration/`, `e2e/`).

**One-time setup**

1. Install dev dependencies:
   ```powershell
   .\venv\Scripts\pip install -r requirements-dev.txt
   .\venv\Scripts\python -m playwright install chromium
   ```
2. Apply the NEXORA_TEST DDL block from `environment_transfer_queries.tmp.sql` to the SQL Server.
3. Copy `TEST.env.example` to `TEST.env` and fill in your test SQL Server credentials.
4. Reset NEXORA_TEST to a clean state:
   ```powershell
   .\scripts\test-db-reset.ps1
   ```
5. Install the local pre-push git hook:
   ```powershell
   .\scripts\install-hooks.ps1
   ```

**Running tests locally**

```powershell
.\venv\Scripts\python -m pytest tests -v --reruns 2 --only-rerun flaky_e2e
```

The pre-push hook runs the same command on every `git push`. Bypass it with `git push --no-verify` (CI will still gate the deploy).

**CI**

Pushes to `main` run the `test` job in `.github/workflows/deploy.yml`. If it fails, the `deploy` job is skipped. Test reports (`junit.xml`, `report.html`) are uploaded as a workflow artifact named `test-results`.
```

- [ ] **Step 18.2: Stop here. Show user the diff**

User commits.

---

**Task 19: End-to-end CI gate verification**

This task verifies on a PR — without ever pushing to main — that the gate works. The PR setup from Task 17 makes this clean: PRs run `test` only; only push-to-main runs `deploy`.

- [ ] **Step 19.1: Open a PR for this whole branch**

After Tasks 1-18 are all committed on the feature branch, push the branch:

```powershell
git push origin <feature-branch-name>
```

Open a PR against `main` via the GitHub UI. The `test` job will fire on the PR.

- [ ] **Step 19.2: Confirm the test job runs and passes on the PR**

Watch the workflow run in the GitHub Actions UI. Expected: `test` runs (≈3 min), passes, uploads `test-results` artifact. `deploy` does NOT run (skipped by the `if:` guard — this is correct, we don't deploy from a PR).

Download the `test-results` artifact and confirm `junit.xml` and `report.html` are present and show all tests passing.

- [ ] **Step 19.3: Add a deliberately failing test, push, watch the gate fail**

On the same PR branch:

```powershell
git switch <feature-branch-name>
```

Append to `tests/unit/test_security.py`:

```python
def test_intentional_failure_for_gate_verification():
    assert False, "DELETE ME — verifying that the CI gate blocks deploys"
```

Push:

```powershell
git push --no-verify origin <feature-branch-name>
```

`--no-verify` skips the local pre-push hook so the push reaches CI even though tests are broken.

In the GitHub Actions UI: the `test` job runs and FAILS. `deploy` does not run. PR status check is red. This is the gate working.

- [ ] **Step 19.4: Remove the failing test, push, watch the gate pass**

```powershell
git switch <feature-branch-name>
```

Remove `test_intentional_failure_for_gate_verification` from `tests/unit/test_security.py`. Run locally to confirm the suite is green:

```powershell
.\venv\Scripts\python -m pytest tests -q --reruns 2 --only-rerun flaky_e2e
```

Push (local hook will run — that's the point, it should now pass and allow the push):

```powershell
git push origin <feature-branch-name>
```

Watch the `test` job pass on the PR. PR status check is green.

- [ ] **Step 19.5: Merge the PR**

After review, merge the PR. The push to `main` triggers BOTH `test` and `deploy`. `test` passes → `deploy` runs → IIS pool restarts with new code. Confirm the production app at the usual URL is up.

If `test` ever fails on `main` (e.g. a flake, a regression), `deploy` is skipped automatically. Pool stays on the previous code. This is the steady state.

- [ ] **Step 19.6: Stop here. Show user the PR merge result and final workflow run output**

Per CLAUDE.md, the user owns the merge. Surface the PR URL and the workflow run URL; user merges and confirms production is healthy.

---

**Acceptance check (run at end)**

After all tasks are complete, run the full suite locally and confirm CI artifacts:

```powershell
.\scripts\test-db-reset.ps1
.\venv\Scripts\python -m pytest tests -v --reruns 2 --only-rerun flaky_e2e
```

Expected: 15 passed (8 unit + 6 integration + 1 e2e). `test-results/junit.xml` and `test-results/report.html` exist and contain results.

Push the branch via PR. Confirm in the GitHub Actions UI:

- `test` job runs first, passes, takes ~3 min
- `deploy` job runs after, takes the original ~2-3 min
- Test artifacts are downloadable

If everything passes, the gate is live.

