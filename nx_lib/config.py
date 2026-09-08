"""Environment-driven configuration for nexora.

Loaded once at import time. Reads ``env/{ENVIRONMENT}.env`` (falling back,
with a ``DeprecationWarning``, to a root-level ``{ENVIRONMENT}.env`` for one
release while operators move files into ``env/`` on shared hosts) *before*
the default root ``.env``, so secrets in env/INT.env / env/PROD.env take
precedence over the root .env fallback. A value already present in the
process environment always wins over both files, since ``load_dotenv``
never overrides an existing OS env var (``override=False`` throughout):
OS env > env-specific file > root .env.
"""

import os
import warnings
from datetime import timedelta
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# How long a signed-in session stays valid. Applied to Flask's
# PERMANENT_SESSION_LIFETIME in create_app(), and read by
# ops/cleanup/prune_active_sessions.py to derive its retention window. It lives
# here rather than inline in create_app() so the cleanup cannot fall out of step
# with it: a cleanup that deletes rows younger than a live session would log
# people out (#227).
SESSION_LIFETIME = timedelta(hours=24)

# Grace added on top of SESSION_LIFETIME before an ActiveSessions row is pruned.
# The row is only ever read within 30 minutes of LastSeenAt (the admin overview
# count and the live-sessions list both filter to that), so this window is pure
# slack for clock skew and suspended machines rather than anything functional.
SESSION_ROW_RETENTION_GRACE = timedelta(days=7)


def _load_env_files(repo_root: Path, env_name: str) -> None:
    """Load dotenv files in OS-env > env-specific-file > root-.env order.

    ``load_dotenv`` defaults to ``override=False``, so a key already set in
    the process environment is never touched by either file; between the
    two files, whichever loads first wins for a given key — hence the
    env-specific file loads before the root .env fallback. Extracted so
    tests/unit/test_config_dotenv.py can exercise the precedence against
    tmp files instead of the real repo tree.
    """
    primary_env_file = repo_root / "env" / f"{env_name}.env"
    legacy_env_file = repo_root / f"{env_name}.env"
    root_env_file = repo_root / ".env"

    # Env-specific secrets. Prefer env/{ENV}.env (PR 8 layout); fall back to
    # the legacy root-level {ENV}.env for one release while shared hosts
    # (SYAPP01) catch up. The fallback emits a DeprecationWarning so it
    # shows up in app logs and reminds operators to move the file.
    if primary_env_file.exists():
        load_dotenv(dotenv_path=primary_env_file)
    elif legacy_env_file.exists():
        load_dotenv(dotenv_path=legacy_env_file)
        warnings.warn(
            f"Loaded env from legacy root location {legacy_env_file}. "
            f"Move to {primary_env_file} (PR 8 of dev-env upgrade); the "
            f"fallback will be removed after one release.",
            DeprecationWarning,
            stacklevel=2,
        )

    # Root .env loads last: lowest precedence, never overrides a value
    # already set by the OS environment or the env-specific file above.
    load_dotenv(dotenv_path=root_env_file)


# ENVIRONMENT itself has to be known before we can pick which env/{ENV}.env
# file to load. Prefer the real process environment; else peek at the root
# .env without mutating os.environ (dotenv_values just parses the file), so
# local setups that only set ENVIRONMENT via the root .env still resolve the
# right per-environment file instead of silently loading none of it.
_env_name = (
    os.environ.get("ENVIRONMENT") or dotenv_values(REPO_ROOT / ".env").get("ENVIRONMENT") or ""
)

_pre_dotenv_keys = frozenset(os.environ)
_load_env_files(REPO_ROOT, _env_name)
# Keys that came from the .env files rather than the real OS environment.
# Child processes that must re-resolve their own env file (the dev-server
# restart-with-env-switch, #187) strip these before spawning — otherwise the
# inherited values win over the new env file (override=False) and the child
# runs the old environment's connections under the new environment's name.
DOTENV_KEYS = frozenset(os.environ) - _pre_dotenv_keys

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
    # Uploaded org logos (#98 phase 4). Not under uploads/ -- unrelated
    # lifecycle/permission model. Created lazily on first upload (Task 11),
    # mirroring uploads/avatars/; nothing to read before that exists.
    branding = VAR_DIR / "branding"


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
# Third read-only login for the SQL sandbox: db_datareader on the Generali
# tenant DB only. Same graceful-degrade contract -- unset means that target
# answers 503 rather than falling back to the app's read-write login.
DB_REPORTING_GENERALI_RO_USER = os.environ.get("DB_REPORTING_GENERALI_RO_USER")
DB_REPORTING_GENERALI_RO_PWD = os.environ.get("DB_REPORTING_GENERALI_RO_PWD")

# SQL Server ODBC driver + TLS knobs (#193 finding 16). Defaults preserve
# today's behavior (legacy unencrypted "{SQL Server}" driver) since flipping
# the default blind could break connectivity on a box without the modern
# driver installed -- set DB_ODBC_DRIVER to "ODBC Driver 17 for SQL Server"
# (or 18) once it's confirmed installed on that box, which also turns on
# Encrypt=yes/TrustServerCertificate=yes below (the legacy driver doesn't
# understand those params).
DB_ODBC_DRIVER = os.environ.get("DB_ODBC_DRIVER", "SQL Server")
DB_ODBC_ENCRYPT = DB_ODBC_DRIVER != "SQL Server"

# Support inbox the outage monitor (ops/outage_monitor.py) files tickets to.
# Unset -> the monitor still probes and logs but sends no mail, so a dev box
# never pages support.
SUPPORT_MAIL = os.environ.get("SUPPORT_MAIL")
# Public URL the outage monitor GETs to prove IIS + the app pool are alive.
OUTAGE_SITE_URL = os.environ.get("OUTAGE_SITE_URL", "https://nexora.sydoc.ch/nexora/")
# Monitor-only key from dbo.ApiKeys, used to probe the external API's full auth
# path against its /api/test/v1 twin. Unset -> that probe skips itself.
OUTAGE_API_KEY = os.environ.get("OUTAGE_API_KEY")

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

# MS02 dashboard-statistics DB (separate Postgres DB "Praesidialdepartement_BS"
# on the same Azure host/login as the MS02 runtime DB). A PG connection is bound
# to one database, so the stats DB needs its own engine. Defaults reuse the
# MS02_DB_* server/login with dbname=Praesidialdepartement_BS.
MS02_STATS_DB_HOST = os.environ.get("MS02_STATS_DB_HOST", MS02_DB_HOST)
MS02_STATS_DB_NAME = os.environ.get("MS02_STATS_DB_NAME", "Praesidialdepartement_BS")
MS02_STATS_DB_USER = os.environ.get("MS02_STATS_DB_USER", MS02_DB_USER)
MS02_STATS_DB_PWD = os.environ.get("MS02_STATS_DB_PWD", MS02_DB_PWD)
MS02_STATS_DB_PORT = os.environ.get("MS02_STATS_DB_PORT", MS02_DB_PORT)

# MS02 doc-field index DB (separate Postgres DB on the same Azure host/login as
# the MS02 runtime DB, but a DIFFERENT database name). A PG connection is bound
# to one database, so the doc-field index needs its own engine. Defaults reuse
# the MS02_DB_* server/login/port/TLS; ONLY the dbname differs and has NO safe
# default -- the owner supplies MS02_DOCFIELDS_DB_NAME. Until it is set the
# engine degrades to None and doc-field searches FAIL CLOSED for MS02: the
# Postgres source contributes zero rows to any doc-field-filtered list (an
# unset engine must never mean "unconstrained" -- that flooded STAGING
# search results with the entire MS02 corpus, 2026-07-20).
MS02_DOCFIELDS_DB_HOST = os.environ.get("MS02_DOCFIELDS_DB_HOST", MS02_DB_HOST)
MS02_DOCFIELDS_DB_NAME = os.environ.get("MS02_DOCFIELDS_DB_NAME")
MS02_DOCFIELDS_DB_USER = os.environ.get("MS02_DOCFIELDS_DB_USER", MS02_DB_USER)
MS02_DOCFIELDS_DB_PWD = os.environ.get("MS02_DOCFIELDS_DB_PWD", MS02_DB_PWD)
MS02_DOCFIELDS_DB_PORT = os.environ.get("MS02_DOCFIELDS_DB_PORT", MS02_DB_PORT)

CSP = {
    "default-src": "'self'",
    "base-uri": "'self'",
    "object-src": "'none'",
    "script-src": [
        "'self'",
        # No 'unsafe-inline' (#193 finding 10) -- every inline <script> is
        # nonce-gated instead (content_security_policy_nonce_in in
        # nx_lib/__init__.py, csp_nonce() in each template). Inline
        # onclick/onchange/... attribute handlers are not covered by a
        # script-src nonce, so those were converted to addEventListener
        # bindings rather than allowed via 'unsafe-hashes'.
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
