"""Environment-driven configuration for nexora.

Loaded once at import time. Reads ``.env`` then ``env/{ENVIRONMENT}.env`` so
secrets in env/INT.env / env/PROD.env override anything in the default .env
file. Falls back to a root-level ``{ENVIRONMENT}.env`` with a
``DeprecationWarning`` for one release while operators move files into
``env/`` on shared hosts.
"""

import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# Step 1: root .env (environment-selector; sets ENVIRONMENT=INT|PROD|... so
# the second load_dotenv knows which secrets file to read).
load_dotenv()

# Step 2: env-specific secrets. Prefer env/{ENV}.env (PR 8 layout); fall
# back to the legacy root-level {ENV}.env for one release while shared
# hosts (SYAPP01) catch up. The fallback emits a DeprecationWarning so the
# warning shows up in app logs and reminds operators to move the file.
_env_name = os.environ.get("ENVIRONMENT", "")
_primary_env_file = REPO_ROOT / "env" / f"{_env_name}.env"
_legacy_env_file = REPO_ROOT / f"{_env_name}.env"

if _primary_env_file.exists():
    load_dotenv(dotenv_path=_primary_env_file)
elif _legacy_env_file.exists():
    load_dotenv(dotenv_path=_legacy_env_file)
    warnings.warn(
        f"Loaded env from legacy root location {_legacy_env_file}. "
        f"Move to {_primary_env_file} (PR 8 of dev-env upgrade); the "
        f"fallback will be removed after one release.",
        DeprecationWarning,
        stacklevel=2,
    )

IS_PROD = os.environ.get("ENVIRONMENT") == "PROD"

# --- Runtime paths -----------------------------------------------------------
# Every runtime-writable dir lives under var/. Gitignored except .gitkeep.
VAR_DIR = REPO_ROOT / "var"


class PATHS:
    """Runtime data paths. All under var/, all gitignored."""

    uploads = VAR_DIR / "uploads"
    session = VAR_DIR / "session"
    logs = VAR_DIR / "logs"
    screenshots = VAR_DIR / "screenshots"
    backups = VAR_DIR / "backups"
    test_results = VAR_DIR / "test-results"


# Only mkdir the dirs Flask actively writes to. screenshots/, backups/, and
# test_results/ are dev/test conventions — created by bootstrap.ps1 for dev
# clones and by pytest at first run; creating them at app import would leave
# empty dev-only folders on prod's \\syapp01\nexora\var\.
for _p in (
    PATHS.uploads,
    PATHS.session,
    PATHS.logs,
):
    _p.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")

DB_UID = os.environ.get("DB_UID")
DB_PWD = os.environ.get("DB_PWD")
DB_SERVER_PRD = os.environ.get("DB_SERVER_PRD")
DB_NEXORA = os.environ.get("DB_NEXORA")
DB_STATISTICS = os.environ.get("DB_STATISTICS")
DB_OCTO_RUNTIME = os.environ.get("DB_OCTO_RUNTIME")
DB_GENERALI = os.environ.get("DB_GENERALI", "Generali")

GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
GRAPH_USERNAME = os.environ.get("GRAPH_USERNAME")
GRAPH_PASSWORD = os.environ.get("GRAPH_PASSWORD")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET")

OCTO_CLIENT_SECRET = os.environ.get("OCTO_CLIENT_SECRET")
OCTO_CLIENT_ID = os.environ.get("OCTO_CLIENT_ID")
OCTO_GRANT_TYPE = os.environ.get("OCTO_GRANT_TYPE")
OCTO_DOMAIN = os.environ.get("OCTO_DOMAIN")

BEXIO_PAT = os.environ.get("BEXIO_PAT")

CSP = {
    "default-src": "'self'",
    "base-uri": "'self'",
    "object-src": "'none'",
    "script-src": [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.tailwindcss.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ],
    "style-src": [
        "'self'",
        "'unsafe-inline'",
        "https://fonts.googleapis.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ],
    "font-src": [
        "'self'",
        "https://fonts.gstatic.com",
        "https://cdnjs.cloudflare.com",
    ],
    "img-src": [
        "'self'",
        "data:",
        "blob:",
        "https://cdn.tailwindcss.com",
    ],
    "connect-src": [
        "'self'",
        "https://cdn.tailwindcss.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ],
}
