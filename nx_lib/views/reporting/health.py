"""Reporting: source health + schema introspection routes (beautify-phase-2a,
Task 3).

``/api/reporting/sources/health`` (Console sources rail status dots) and
``/api/reporting/sources/<id>/schema`` (Console source visualizer). Split out
of ``nx_lib/views/reporting/__init__.py`` — see that module's docstring for
the package's overall shape.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait as futures_wait

import pyodbc
from flask import current_app, jsonify, session
from flask_babel import gettext as _

from ... import mapping_config
from ...db import engine_statistics_db
from ...reporting import db_schema
from ...reporting.sources import accessible
from ...security import require_permission
from ._shared import _CURATED_ENGINES, _SQL_TARGET_ENGINES, _effective_sources

# Health-probe budget (Console rail): every distinct engine is probed
# concurrently against ONE shared deadline (same bounded-parallel idiom as
# nx_lib.db.ping_dbs_parallel) so N down engines cost ~0.8s total, never N
# sequential unbounded driver-timeout waits. A dedicated small pool keeps this
# route's probes off ping_dbs_parallel's own executor (used by the admin
# overview / outage monitor / doctor health checks).
_HEALTH_PROBE_TIMEOUT_S = 0.8

# Per-probe ODBC login timeout (seconds). Only nx_lib/db.py's engine_nexora_db
# has a permanent LoginTimeout baked into its connection string (Task 4, D3 --
# every other engine's pool config is deliberately unchanged). Without a
# bound here, a probe against any OTHER down engine can occupy a worker in
# _health_probe_executor's small pool for the ODBC driver's ~15s default --
# with 2+ down engines and the Console's repeated polling, the 8-worker pool
# saturates and a probe for a genuinely healthy engine that never gets a
# worker inside the 0.8s deadline incorrectly reports ok=False. This is a
# probe-specific bound (health checks only), not a change to any engine's own
# pool/connection settings -- narrower than, and does not conflict with, D3's
# "other engines unchanged" call on POOL SIZING.
_PROBE_LOGIN_TIMEOUT_S = 5
_health_probe_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="reporting-health")


def _probe_engine(engine, login_timeout_s=_PROBE_LOGIN_TIMEOUT_S):
    """(ok, latency_ms, db_name) for one probe round-trip; DB_NAME() rides
    along because the engines are built from odbc_connect strings whose
    SQLAlchemy URL carries no database attribute.

    Connects directly via pyodbc with a bounded login timeout instead of
    going through the engine's pool (``engine.raw_connection()``) -- same
    idea as engine_nexora_db's own ``LoginTimeout=5``, just applied per-probe
    instead of baked into the engine permanently. Falls back to
    ``engine.raw_connection()`` for an engine that isn't ODBC-based (no
    ``odbc_connect`` in its URL), which keeps the old unbounded behavior for
    that engine rather than guessing at a dialect-appropriate timeout param.
    """
    if engine is None:
        return False, None, None
    t0 = time.perf_counter()
    try:
        odbc_connect = engine.url.query.get("odbc_connect")
        if odbc_connect:
            conn = pyodbc.connect(odbc_connect, timeout=login_timeout_s)
        else:
            conn = engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT DB_NAME()")
            row = cur.fetchone()
        finally:
            conn.close()
        return True, (time.perf_counter() - t0) * 1000.0, (row[0] if row else None)
    except Exception:
        return False, None, None


def _probe_engines_parallel(engines, timeout_s=_HEALTH_PROBE_TIMEOUT_S):
    """Probe each distinct engine in ``engines`` concurrently, bounded by one
    shared deadline. Returns {id(engine): (ok, latency_ms, db_name)}; an
    engine still running past the deadline reports as not-ok/timed-out rather
    than blocking the request."""
    entries = [(engine, _health_probe_executor.submit(_probe_engine, engine)) for engine in engines]
    _done, not_done = futures_wait([fut for _engine, fut in entries], timeout=timeout_s)
    results = {}
    for engine, fut in entries:
        if fut in not_done:
            fut.cancel()
            results[id(engine)] = (False, None, None)
        else:
            results[id(engine)] = fut.result()
    return results


@require_permission("reporting.view")
def api_sources_health():
    """Live status dot + latency per accessible source (Console rail).
    One DB_NAME() probe per distinct engine, shared across sources, all
    fired concurrently with a shared 0.8s deadline."""
    perms = set(session.get("permissions", []))
    sources = accessible(_effective_sources(), perms)

    engines_by_id = {}  # id(engine) -> engine
    engine_id_for_source = {}  # source id -> id(engine)
    for s in sources:
        if s["kind"] == "sql":
            engine = _SQL_TARGET_ENGINES.get(s.get("target", "statistics"))
        else:
            engine = _CURATED_ENGINES.get(s.get("engine"), engine_statistics_db)
        engines_by_id[id(engine)] = engine
        engine_id_for_source[s["id"]] = id(engine)

    probe_results = _probe_engines_parallel([e for e in engines_by_id.values() if e is not None])

    out = []
    for s in sources:
        engine_id = engine_id_for_source[s["id"]]
        ok, ms, db_name = probe_results.get(engine_id, (False, None, None))
        out.append(
            {
                "id": s["id"],
                "ok": ok,
                "latencyMs": round(ms, 1) if ms is not None else None,
                "db": db_name,
            }
        )
    return jsonify({"sources": out})


def _source_used_tables(src):
    """Qualified table names the reporting layer actually reads for `src`.

    Two registries know this: the source's own `BaseObject` (the generic
    `table` provider's target) and `dbo.ProcessSources.TableName` (the
    statistik table per client/process, migration 0074). Names from a
    different database simply won't match anything when the payload is
    filtered, so all of them can be thrown in together.
    """
    names = set()
    if src.get("baseObject"):
        names.add(src["baseObject"])
    reg = mapping_config.registry()
    if reg is not None:
        names |= {ps.table for ps in reg.sources.values() if ps.table}
    return names


@require_permission("reporting.sources.schema")
def api_source_schema(source_id):
    """Tables, columns and foreign keys of the database behind one source.

    Feeds the Console's source visualizer (click a rail card): a filterable
    table list and an ER diagram. Read-only catalog queries on the same engine
    the source itself reads from, so no new credential surface -- but the
    schema of a whole database is more than the source's own fields, hence its
    own grant on top of the source's permission.
    """
    perms = set(session.get("permissions", []))
    src = next(
        (s for s in accessible(_effective_sources(), perms) if s.get("id") == source_id),
        None,
    )
    if src is None:
        return jsonify({"error": _("Not authorized for this source")}), 403
    if src["kind"] == "sql":
        engine = _SQL_TARGET_ENGINES.get(src.get("target", "statistics"))
    else:
        engine = _CURATED_ENGINES.get(src.get("engine"), engine_statistics_db)
    if engine is None:
        return jsonify({"error": _("This source's database is not configured.")}), 503
    try:
        conn = engine.raw_connection()
    except Exception as e:
        current_app.logger.warning(f"reporting schema: connect failed for {source_id}: {e}")
        return jsonify({"error": _("Could not reach this database.")}), 503
    try:
        payload = db_schema.filter_used(db_schema.introspect(conn), _source_used_tables(src))
    except Exception as e:
        current_app.logger.error(f"reporting schema: introspection failed for {source_id}: {e}")
        return jsonify({"error": _("Could not read this database's schema.")}), 502
    finally:
        conn.close()
    payload["source"] = source_id
    payload["label"] = src.get("label")
    return jsonify(payload)


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/sources/health",
        endpoint="reporting_sources_health",
        view_func=api_sources_health,
    )
    app.add_url_rule(
        "/api/reporting/sources/<source_id>/schema",
        endpoint="reporting_source_schema",
        view_func=api_source_schema,
    )
