# Nexora test suite

## Layout

- `tests/unit/` — pure-logic + DB-touching unit tests. One file per `nx_lib/*` module.
- `tests/integration/` — Flask test client tests. One file per `nx_lib/views/*` module.
- `tests/e2e/` — Playwright tests. One file per page template.

## Fixtures (see `conftest.py`)

| Fixture | What it gives you |
| --- | --- |
| `app` | Flask app, session-scoped |
| `client` | Flask test client, function-scoped |
| `db_conn` | SQLAlchemy connection inside a transaction that rolls back |
| `totp_for` | Compute the current TOTP code for a seeded user |
| `login` | Function that logs you in as a given seed user and returns the client |
| `admin_client` / `user_client` / `noperm_client` | Pre-logged-in clients |
| `auth_app_ctx` | Pushes `app_context()` for tests that need `current_app` |
| `fake_session` | Dict masquerading as `nx_lib.security.session` |
| `seeded_org` | The `"TEST"` organizationcode that seed users belong to |

## Seed users

All three live in `sql/test/seed.sql`. Password is `Test1234!`. All have `twoFA=1` so `/login` always redirects to `/verify_2fa`.

| Username | Access profile | Permissions |
| --- | --- | --- |
| `admin@test.local` | TestAdmin | `admin.view`, `admin.users.manage`, `dashboard.view` |
| `user@test.local` | TestUser | `dashboard.view` only |
| `noperm@test.local` | TestNoPerm | none |

## Patterns

**Unit test — pure function, no DB**

```python
from nx_lib.process_helpers import normalize_process_selection

def test_normalize_process_selection_falls_back_to_all():
    value, targets = normalize_process_selection("", ["Sydoc.Invoices"])
    assert value == "all"
    assert targets == ["Sydoc.Invoices"]
```

**Unit test — function that reads `session`**

```python
from nx_lib.security import has_permission

def test_has_permission_true(fake_session):
    fake_session["permissions"] = ["admin.view"]
    assert has_permission("admin.view") is True
```

**Unit test — function that hits the DB**

```python
from sqlalchemy import text
from nx_lib.security import load_permissions_for_user

def test_load_permissions_for_user(db_conn):
    row = db_conn.execute(
        text("SELECT userid FROM Users WHERE username = 'admin@test.local'")
    ).fetchone()
    perms = load_permissions_for_user(row.userid)
    assert "admin.view" in perms
```

**Integration test — Flask test client**

```python
def test_dashboard_requires_auth(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_dashboard_renders_for_user(user_client):
    resp = user_client.get("/dashboard")
    assert resp.status_code == 200
```

**E2E test — Playwright with `data-testid`**

```python
import pytest
from playwright.sync_api import expect


@pytest.mark.flaky_e2e
def test_dashboard_filter_opens_modal(nexora_server, page):
    page.goto(f"{nexora_server}/dev/login/user@test.local")
    page.wait_for_url("**/dashboard")
    page.locator('[data-testid="dashboard-filter-button"]').click()
    expect(page.locator('[data-testid="dashboard-filter-modal"]')).to_be_visible()
```

The `nexora_server` fixture (in `tests/e2e/conftest.py`) starts `nx_main.py` on port 8765 for the test session. The `/dev/login/<username>` shortcut bypasses the 2FA dance in TEST/INT envs.

## Running

```powershell
# Whole suite with coverage
.\.venv\Scripts\python.exe -m pytest -q

# Just unit
.\.venv\Scripts\python.exe -m pytest tests/unit -q

# Just integration
.\.venv\Scripts\python.exe -m pytest tests/integration -q

# Just e2e (chromium)
.\.venv\Scripts\python.exe -m pytest tests/e2e -q

# E2E cross-browser
.\.venv\Scripts\python.exe -m pytest tests/e2e --browser chromium --browser firefox --browser webkit

# Suppress coverage (faster local iteration)
.\.venv\Scripts\python.exe -m pytest --no-cov tests/

# Single test, verbose
.\.venv\Scripts\python.exe -m pytest tests/unit/test_security.py::test_has_permission_returns_true_when_present -v
```

Reports land under `var/test-results/`:
- `junit.xml` — JUnit XML for CI
- `report.html` — full pytest HTML
- `coverage-html/index.html` — coverage HTML
- `coverage.xml` — coverage XML (consumed by `test_coverage_thresholds.py`)

## Coverage gates

- `[tool.coverage.report] fail_under = 0` in `pyproject.toml` — the global floor is 0 so local subset runs don't fail. **Per-module ratcheting** in `tests/unit/test_coverage_thresholds.py:MIN_COVERAGE` is the real gate.
- After adding tests, run the full suite, look at `var/test-results/coverage-html/index.html`, and raise the matching `MIN_COVERAGE` entry. Never lower a threshold without team sign-off.

## Adding tests

- New function in `nx_lib/foo.py` → add a test in `tests/unit/test_foo.py` in the same commit.
- New route in `nx_lib/views/foo.py` → add an integration test in `tests/integration/test_foo_routes.py`.
- New interactive element in a template → add `data-testid="kebab-case-purpose"` to it AND a Playwright assertion that clicking it does the expected thing.
