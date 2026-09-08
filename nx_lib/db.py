"""SQL Server engine factory and DB health-check helpers.

Engines are created once at module-import time using credentials already
loaded into nexora.config. Imports of ``engine_nexora_db`` etc. resolve to
the same singleton objects everywhere.
"""

import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as futures_wait
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from . import config as cfg

# TLS suffix for the modern ODBC drivers (17/18) -- the legacy "{SQL Server}"
# driver doesn't recognize Encrypt/TrustServerCertificate and errors on them,
# so this is only appended when DB_ODBC_DRIVER opts into a modern driver
# (see config.py DB_ODBC_ENCRYPT).
_TLS_SUFFIX = "Encrypt=yes;TrustServerCertificate=yes;" if cfg.DB_ODBC_ENCRYPT else ""


def get_db_url(d: str | None, s: str | None = None, login_timeout: int | None = None) -> str:
    server = s if s is not None else cfg.DB_SERVER_PRD
    login_timeout_suffix = f"LoginTimeout={login_timeout};" if login_timeout is not None else ""
    params = urllib.parse.quote_plus(
        f"DRIVER={{{cfg.DB_ODBC_DRIVER}}};"
        f"SERVER={server},1433;"
        f"DATABASE={d};"
        f"UID={cfg.DB_UID};"
        f"PWD={cfg.DB_PWD};"
        f"{_TLS_SUFFIX}"
        f"{login_timeout_suffix}"
    )
    return f"mssql+pyodbc:///?odbc_connect={params}"


def get_ro_db_url(
    d: str, s: str | None = None, uid: str | None = None, pwd: str | None = None
) -> str:
    """Build a connection URL using a dedicated read-only reporting login.

    Defaults to the Statistics RO login (``DB_REPORTING_RO_*``); pass ``uid`` /
    ``pwd`` to use a different read-only login (e.g. the Octopus target's).
    """
    server = s if s is not None else cfg.DB_SERVER_PRD
    uid = uid if uid is not None else cfg.DB_REPORTING_RO_USER
    pwd = pwd if pwd is not None else cfg.DB_REPORTING_RO_PWD
    params = urllib.parse.quote_plus(
        f"DRIVER={{{cfg.DB_ODBC_DRIVER}}};"
        f"SERVER={server},1433;"
        f"DATABASE={d};"
        f"UID={uid};"
        f"PWD={pwd};"
        f"{_TLS_SUFFIX}"
    )
    return f"mssql+pyodbc:///?odbc_connect={params}"


def get_pg_url(
    host: str,
    db: str,
    uid: str,
    pwd: str,
    port: str = "5432",
    sslmode: str = "require",
    sslrootcert: str | None = None,
) -> URL:
    """Build a SQLAlchemy URL for an Azure Postgres DB over psycopg2 with TLS.

    Uses ``URL.create`` so special characters in the password are handled
    safely (no manual percent-encoding). Azure Postgres requires SSL.

    ``sslmode`` defaults to ``require`` (encrypt, but do not verify the server
    certificate) because psycopg2-binary's bundled libpq has no default CA
    store on Windows, so ``verify-full`` would refuse to connect until an Azure
    root-CA bundle is provisioned. To close the MITM gap, set ``sslmode`` to
    ``verify-full`` (or ``verify-ca``) and pass ``sslrootcert`` pointing at that
    bundle — see the MS02_DB_SSLMODE / MS02_DB_SSLROOTCERT config knobs.
    """
    query = {"sslmode": sslmode}
    if sslrootcert:
        query["sslrootcert"] = sslrootcert
    return URL.create(
        "postgresql+psycopg2",
        username=uid,
        password=pwd,
        host=host,
        port=int(port),
        database=db,
        query=query,
    )


engine_octo_db = create_engine(
    get_db_url(cfg.DB_OCTO_RUNTIME),
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)

# NexoraDB is touched by every request (session/permission hooks), so its pool
# is sized to never make the 32 waitress threads queue: pool_size=32 covers a
# full thread complement, max_overflow=16 gives headroom for a burst.
# LoginTimeout=5 makes a downed DB fail fast (~5s) instead of the ODBC driver's
# ~15s default -- other engines are per-feature, not per-request, so they keep
# the driver default and are deliberately left unchanged.
engine_nexora_db = create_engine(
    get_db_url(cfg.DB_NEXORA, login_timeout=5),
    pool_size=32,
    max_overflow=16,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)
engine_statistics_db = create_engine(
    get_db_url(cfg.DB_STATISTICS),
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)
engine_generali_db = create_engine(
    get_db_url(cfg.DB_GENERALI),
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)

# MS02 client runtime DB (Azure Postgres). Stays None until its env vars are
# provisioned, so dev/test boxes without MS02 credentials boot normally — same
# graceful-degrade pattern as engine_statistics_ro / engine_octo_ro.
if cfg.MS02_DB_HOST and cfg.MS02_DB_NAME and cfg.MS02_DB_USER and cfg.MS02_DB_PWD:
    engine_ms02_pg: Engine | None = create_engine(
        get_pg_url(
            cfg.MS02_DB_HOST,
            cfg.MS02_DB_NAME,
            cfg.MS02_DB_USER,
            cfg.MS02_DB_PWD,
            cfg.MS02_DB_PORT,
            sslmode=cfg.MS02_DB_SSLMODE,
            sslrootcert=cfg.MS02_DB_SSLROOTCERT,
        ),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_ms02_pg = None

# MS02 dashboard-statistics DB (Praesidialdepartement_BS, Azure Postgres).
# Separate engine because a PG connection is bound to one database. Same
# graceful-degrade pattern; reuses the MS02 TLS settings.
if (
    cfg.MS02_STATS_DB_HOST
    and cfg.MS02_STATS_DB_NAME
    and cfg.MS02_STATS_DB_USER
    and cfg.MS02_STATS_DB_PWD
):
    engine_ms02_stats_pg: Engine | None = create_engine(
        get_pg_url(
            cfg.MS02_STATS_DB_HOST,
            cfg.MS02_STATS_DB_NAME,
            cfg.MS02_STATS_DB_USER,
            cfg.MS02_STATS_DB_PWD,
            cfg.MS02_STATS_DB_PORT,
            sslmode=cfg.MS02_DB_SSLMODE,
            sslrootcert=cfg.MS02_DB_SSLROOTCERT,
        ),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_ms02_stats_pg = None

# MS02 doc-field index DB (separate Postgres DB on the same Azure host/login as
# the MS02 runtime DB). A PG connection is bound to one database, so the
# doc-field index needs its own engine -- a third MS02 engine alongside the
# runtime (engine_ms02_pg) and dashboard-stats (engine_ms02_stats_pg) ones.
# Same graceful-degrade pattern; reuses the MS02 TLS settings. Doc-field search
# pre-resolves matches against this DB into a workitem-ID allow-set (it is never
# joined in-query to the runtime DB).
if (
    cfg.MS02_DOCFIELDS_DB_HOST
    and cfg.MS02_DOCFIELDS_DB_NAME
    and cfg.MS02_DOCFIELDS_DB_USER
    and cfg.MS02_DOCFIELDS_DB_PWD
):
    engine_ms02_docfields_pg: Engine | None = create_engine(
        get_pg_url(
            cfg.MS02_DOCFIELDS_DB_HOST,
            cfg.MS02_DOCFIELDS_DB_NAME,
            cfg.MS02_DOCFIELDS_DB_USER,
            cfg.MS02_DOCFIELDS_DB_PWD,
            cfg.MS02_DOCFIELDS_DB_PORT,
            sslmode=cfg.MS02_DB_SSLMODE,
            sslrootcert=cfg.MS02_DB_SSLROOTCERT,
        ),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_ms02_docfields_pg = None

# Read-only engine for the Reporting live-SQL sandbox. Uses a dedicated
# db_datareader-only login over the Statistics DB. Stays None when the RO
# credentials are not provisioned, so the SQL source simply degrades to
# "unavailable" rather than breaking startup on dev/test boxes.
if cfg.DB_REPORTING_RO_USER and cfg.DB_REPORTING_RO_PWD and cfg.DB_STATISTICS:
    engine_statistics_ro: Engine | None = create_engine(
        get_ro_db_url(cfg.DB_STATISTICS),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_statistics_ro = None

# Second read-only engine for the SQL sandbox's Octopus target. Uses its own
# dedicated db_datareader-only login (DB_REPORTING_OCTO_RO_*) over the Octopus
# runtime DB. Stays None until those credentials are provisioned, so the
# Octopus SQL target degrades to "unavailable" rather than breaking startup.
if cfg.DB_REPORTING_OCTO_RO_USER and cfg.DB_REPORTING_OCTO_RO_PWD and cfg.DB_OCTO_RUNTIME:
    engine_octo_ro: Engine | None = create_engine(
        get_ro_db_url(
            cfg.DB_OCTO_RUNTIME,
            uid=cfg.DB_REPORTING_OCTO_RO_USER,
            pwd=cfg.DB_REPORTING_OCTO_RO_PWD,
        ),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_octo_ro = None

# Third read-only engine for the SQL sandbox's Generali target: its own
# db_datareader-only login (DB_REPORTING_GENERALI_RO_*) over the Generali
# tenant DB. Unset -> None -> that target answers 503; it never falls back to
# engine_generali_db (the app's read-write login).
if cfg.DB_REPORTING_GENERALI_RO_USER and cfg.DB_REPORTING_GENERALI_RO_PWD and cfg.DB_GENERALI:
    engine_generali_ro: Engine | None = create_engine(
        get_ro_db_url(
            cfg.DB_GENERALI,
            uid=cfg.DB_REPORTING_GENERALI_RO_USER,
            pwd=cfg.DB_REPORTING_GENERALI_RO_PWD,
        ),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_generali_ro = None

# Dedicated executor for DB health pings so a hung server doesn't block the page.
_db_ping_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="db-ping")


def _ping_db_probe(engine: Engine) -> None:
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
    finally:
        conn.close()


def ping_dbs_parallel(
    targets: list[tuple[Engine, str]], timeout_s: float = 2.0
) -> list[dict[str, Any]]:
    """Ping several engines concurrently. ``targets`` is ``[(engine, label), ...]``.

    Total wall time is bounded by ~timeout_s regardless of how many are down:
    all probes are submitted up front, then awaited with a single shared
    deadline (``concurrent.futures.wait``) instead of waiting on each future's
    own ``timeout_s`` one at a time — the previous approach could take up to
    N * timeout_s wall time when several engines were unreachable.
    """
    started = time.monotonic()
    entries = [
        (label, _db_ping_executor.submit(_ping_db_probe, engine)) for engine, label in targets
    ]
    _done, not_done = futures_wait([fut for _label, fut in entries], timeout=timeout_s)

    results = []
    for label, fut in entries:
        if fut in not_done:
            # cancel() is best-effort: it only takes effect if the probe
            # hasn't started running yet (frees up a worker slot). A probe
            # already in flight keeps running in the background until it
            # finishes on its own -- we just stop waiting on it here and
            # report it as timed out regardless.
            fut.cancel()
            results.append(
                {
                    "label": label,
                    "ok": False,
                    "error": "timeout",
                    "latency_ms": int(timeout_s * 1000),
                }
            )
            continue
        try:
            fut.result()
            results.append(
                {
                    "label": label,
                    "ok": True,
                    "error": None,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
        except Exception as e:
            msg = (str(e).splitlines()[0] if str(e) else "error")[:140]
            results.append(
                {
                    "label": label,
                    "ok": False,
                    "error": msg,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
    return results
