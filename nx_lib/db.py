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
