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
DB_REPORTING_RO_USER = os.environ.get("DB_REPORTING_RO_USER")
DB_REPORTING_RO_PWD = os.environ.get("DB_REPORTING_RO_PWD")
# Dedicated read-only login for the Reporting SQL sandbox's Octopus target.
# Separate from the Statistics RO login above (db_datareader on OctoDB only).
DB_REPORTING_OCTO_RO_USER = os.environ.get("DB_REPORTING_OCTO_RO_USER")
DB_REPORTING_OCTO_RO_PWD = os.environ.get("DB_REPORTING_OCTO_RO_PWD")
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

# --- MS02 client: Azure Postgres runtime DB + second Octo endpoint -----------
# Internal attribute names mirror the default DB_*/OCTO_* set with an MS02_
# prefix; the os.environ.get() keys match env/INT.env, which mirrors the
# default DB_SERVER_PRD / DB_UID / DB_OCTO_RUNTIME and OCTO_* names with an
# MS02_ prefix. Absent on dev/test boxes without MS02 creds -> the engine
# (Task 3) degrades to None and the feature stays dormant.
MS02_DB_HOST = os.environ.get("MS02_DB_SERVER_PRD")
MS02_DB_NAME = os.environ.get("MS02_DB_OCTO_RUNTIME")
MS02_DB_USER = os.environ.get("MS02_DB_UID")
MS02_DB_PWD = os.environ.get("MS02_DB_PWD")
MS02_DB_PORT = os.environ.get("MS02_DB_PORT", "5432")
MS02_OCTO_DOMAIN = os.environ.get("MS02_OCTO_DOMAIN")
MS02_OCTO_CLIENT_ID = os.environ.get("MS02_CLIENT_ID")
MS02_OCTO_CLIENT_SECRET = os.environ.get("MS02_CLIENT_SECRET")
MS02_OCTO_GRANT_TYPE = os.environ.get("MS02_GRANT_TYPE", OCTO_GRANT_TYPE)
# TLS hardening for the MS02 Postgres connection. Default 'require' encrypts but
# does NOT verify the server certificate (psycopg2-binary's libpq has no default
# CA store on Windows, so verify-full refuses to connect until a CA bundle is
# provisioned). To close the MITM gap once the Azure root-CA bundle is on the
# host (dev + prod): set MS02_DB_SSLMODE=verify-full and MS02_DB_SSLROOTCERT to
# the bundle path. See nx_lib/db.get_pg_url.
MS02_DB_SSLMODE = os.environ.get("MS02_DB_SSLMODE", "require")
MS02_DB_SSLROOTCERT = os.environ.get("MS02_DB_SSLROOTCERT")

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
