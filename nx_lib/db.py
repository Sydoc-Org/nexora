"""SQL Server engine factory and DB health-check helpers.

Engines are created once at module-import time using credentials already
loaded into nexora.config. Imports of ``engine_nexora_db`` etc. resolve to
the same singleton objects everywhere.
"""

import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from . import config as cfg


def get_db_url(d, s=None):
    server = s if s is not None else cfg.DB_SERVER_PRD
    params = urllib.parse.quote_plus(
        f"DRIVER={{SQL Server}};"
        f"SERVER={server},1433;"
        f"DATABASE={d};"
        f"UID={cfg.DB_UID};"
        f"PWD={cfg.DB_PWD};"
    )
    return f"mssql+pyodbc:///?odbc_connect={params}"


def get_ro_db_url(d, s=None, uid=None, pwd=None):
    """Build a connection URL using a dedicated read-only reporting login.

    Defaults to the Statistics RO login (``DB_REPORTING_RO_*``); pass ``uid`` /
    ``pwd`` to use a different read-only login (e.g. the Octopus target's).
    """
    server = s if s is not None else cfg.DB_SERVER_PRD
    uid = uid if uid is not None else cfg.DB_REPORTING_RO_USER
    pwd = pwd if pwd is not None else cfg.DB_REPORTING_RO_PWD
    params = urllib.parse.quote_plus(
        f"DRIVER={{SQL Server}};"
        f"SERVER={server},1433;"
        f"DATABASE={d};"
        f"UID={uid};"
        f"PWD={pwd};"
    )
    return f"mssql+pyodbc:///?odbc_connect={params}"


def get_pg_url(host, db, uid, pwd, port="5432"):
    """Build a SQLAlchemy URL for an Azure Postgres DB over psycopg2 with TLS.

    Uses ``URL.create`` so special characters in the password are handled
    safely (no manual percent-encoding). Azure Postgres requires SSL.
    """
    return URL.create(
        "postgresql+psycopg2",
        username=uid,
        password=pwd,
        host=host,
        port=int(port),
        database=db,
        query={"sslmode": "require"},
    )


engine_octo_db = create_engine(
    get_db_url(cfg.DB_OCTO_RUNTIME),
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)
engine_nexora_db = create_engine(
    get_db_url(cfg.DB_NEXORA),
    pool_size=10,
    max_overflow=20,
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
    engine_ms02_pg = create_engine(
        get_pg_url(
            cfg.MS02_DB_HOST,
            cfg.MS02_DB_NAME,
            cfg.MS02_DB_USER,
            cfg.MS02_DB_PWD,
            cfg.MS02_DB_PORT,
        ),
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
else:
    engine_ms02_pg = None

# Read-only engine for the Reporting live-SQL sandbox. Uses a dedicated
# db_datareader-only login over the Statistics DB. Stays None when the RO
# credentials are not provisioned, so the SQL source simply degrades to
# "unavailable" rather than breaking startup on dev/test boxes.
if cfg.DB_REPORTING_RO_USER and cfg.DB_REPORTING_RO_PWD and cfg.DB_STATISTICS:
    engine_statistics_ro = create_engine(
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
    engine_octo_ro = create_engine(
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

# Dedicated executor for DB health pings so a hung server doesn't block the page.
_db_ping_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="db-ping")


def _ping_db_probe(engine):
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
    finally:
        conn.close()


def ping_db(engine, label, timeout_s=2.0):
    """Probe a SQLAlchemy engine with SELECT 1, enforcing a wall-clock timeout.

    Never raises. Returns ``{'label', 'ok', 'error', 'latency_ms'}``. If the
    probe doesn't finish within ``timeout_s``, returns ``ok=False`` with
    ``error='timeout'`` — the underlying thread keeps running in the
    background until the OS connect timeout fires, but the caller is unblocked.
    """
    start = time.monotonic()
    future = _db_ping_executor.submit(_ping_db_probe, engine)
    try:
        future.result(timeout=timeout_s)
        return {
            "label": label,
            "ok": True,
            "error": None,
            "latency_ms": int((time.monotonic() - start) * 1000),
        }
    except FuturesTimeoutError:
        return {
            "label": label,
            "ok": False,
            "error": "timeout",
            "latency_ms": int(timeout_s * 1000),
        }
    except Exception as e:
        msg = (str(e).splitlines()[0] if str(e) else "error")[:140]
        return {
            "label": label,
            "ok": False,
            "error": msg,
            "latency_ms": int((time.monotonic() - start) * 1000),
        }


def ping_dbs_parallel(targets, timeout_s=2.0):
    """Ping several engines concurrently. ``targets`` is ``[(engine, label), ...]``.

    Total wall time is bounded by ~timeout_s regardless of how many are down.
    """
    futures = [
        (label, _db_ping_executor.submit(_ping_db_probe, engine), time.monotonic())
        for engine, label in targets
    ]
    results = []
    for label, fut, started in futures:
        try:
            fut.result(timeout=timeout_s)
            results.append(
                {
                    "label": label,
                    "ok": True,
                    "error": None,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
        except FuturesTimeoutError:
            results.append(
                {
                    "label": label,
                    "ok": False,
                    "error": "timeout",
                    "latency_ms": int(timeout_s * 1000),
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
