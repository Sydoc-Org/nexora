"""Client registry: maps each tenant to its runtime DB engine + Octo creds.

Module graph (no cycles): clients -> config, db. octo and workitem_sources
import clients; clients imports neither.
"""

import logging
from dataclasses import dataclass

from . import config as cfg
from .db import (
    engine_ms02_docfields_pg,
    engine_ms02_pg,
    engine_ms02_stats_pg,
    engine_nexora_db,
    engine_octo_db,
    engine_statistics_db,
)

logger = logging.getLogger(__name__)

# Why a module attribute and not just the logger: _build_clients() runs at
# import time, BEFORE Flask configures logging, so the logger.error() below
# reaches stderr (waitress-stdout*) but never app.log and nothing surfaces it
# in the UI. When dbo.Clients cannot be read the registry silently collapses to
# 'default' only -- every non-default runtime (MS02) disappears for the whole
# process lifetime, until the next app-pool recycle. Recording the reason here
# lets /admin/clients and /admin/status show an operator that what they are
# looking at is not what the app is actually running on.
#
# Deliberately NOT a retry loop or a TTL: CLIENTS staying import-time-only is a
# locked decision (spec D4) -- this only makes the degradation visible.
REGISTRY_DEGRADED_REASON = None


def _engines():
    """{RuntimeEngineKey/StatsEngineKey/DocfieldsEngineKey -> engine object}.

    Built fresh on every call (not hoisted to a module-level dict) so it reads
    whatever engine_octo_db etc. currently resolve to -- tests monkeypatch
    those module globals per-test, and a dict built once at import time
    wouldn't see that.
    """
    return {
        "engine_octo_db": engine_octo_db,
        "engine_statistics_db": engine_statistics_db,
        "engine_ms02_pg": engine_ms02_pg,
        "engine_ms02_stats_pg": engine_ms02_stats_pg,
        "engine_ms02_docfields_pg": engine_ms02_docfields_pg,
    }


# The engine-key names dbo.Clients rows may reference -- derived from _engines()
# rather than hand-written a second time, so adding an engine there can't leave
# nx_lib/views/admin/clients.py rejecting a legitimate key. Only the *keys* are frozen
# at import; the engine objects are re-read per call by _engines().
_ENGINE_KEYS = tuple(_engines())


@dataclass(frozen=True)
class ClientConfig:
    code: str
    runtime_engine: object
    dialect: str  # "tsql" | "postgres"
    octo_domain: str | None
    octo_client_id: str | None
    octo_secret: str | None
    octo_grant_type: str | None
    stats_engine: object = None
    stats_dialect: str = "tsql"
    docfields_engine: object = None
    docfields_dialect: str = "tsql"


def _hardcoded_default():
    """The pre-0079 hardcoded 'default'-only registry, used as a fallback when
    dbo.Clients can't be loaded (e.g. the TEST environment has no such table)."""
    return {
        "default": ClientConfig(
            code="default",
            runtime_engine=engine_octo_db,
            dialect="tsql",
            octo_domain=cfg.OCTO_DOMAIN,
            octo_client_id=cfg.OCTO_CLIENT_ID,
            octo_secret=cfg.OCTO_CLIENT_SECRET,
            octo_grant_type=cfg.OCTO_GRANT_TYPE,
            stats_engine=engine_statistics_db,
            stats_dialect="tsql",
            docfields_engine=engine_statistics_db,
            docfields_dialect="tsql",
        ),
    }


def _creds_for(secret_ref):
    """(domain, client_id, secret, grant_type) for an env-key prefix; None ref = unprefixed."""
    p = f"{secret_ref}_" if secret_ref else ""
    return (
        getattr(cfg, f"{p}OCTO_DOMAIN", None),
        getattr(cfg, f"{p}OCTO_CLIENT_ID", None),
        getattr(cfg, f"{p}OCTO_CLIENT_SECRET", None),
        getattr(cfg, f"{p}OCTO_GRANT_TYPE", None),
    )


def _build_clients():
    """Active rows of dbo.Clients (migration 0079), each resolved to a runtime
    engine object (by RuntimeEngineKey) and Octo creds (by SecretRef prefix).
    A row is skipped when its runtime engine is unavailable (None) or its
    resolved Octo domain is falsy -- generalises the pre-0079 MS02 guard
    ``if engine_ms02_pg is not None and cfg.MS02_OCTO_DOMAIN:``.

    Any load failure (e.g. dbo.Clients missing, as on TEST) falls back to the
    hardcoded default-only registry so the app still boots.
    """
    global REGISTRY_DEGRADED_REASON
    REGISTRY_DEGRADED_REASON = None
    engines = _engines()

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT ClientCode, DisplayName, Dialect, RuntimeEngineKey, "
            "StatsEngineKey, StatsDialect, DocfieldsEngineKey, DocfieldsDialect, "
            "OctoDomain, SecretRef, IsActive FROM Clients WHERE IsActive = 1"
        )
        rows = cur.fetchall()

        result = {}
        default_skip_reason = None
        for r in rows:
            if not r.IsActive:
                continue
            runtime_engine = engines.get(r.RuntimeEngineKey)
            env_domain, client_id, secret, grant_type = _creds_for(r.SecretRef)
            octo_domain = r.OctoDomain or env_domain
            if runtime_engine is None or not octo_domain:
                if r.ClientCode == "default":
                    reasons = []
                    if runtime_engine is None:
                        reasons.append(f"unresolved RuntimeEngineKey {r.RuntimeEngineKey!r}")
                    if not octo_domain:
                        reasons.append("no resolvable Octo domain")
                    default_skip_reason = " and ".join(reasons)
                continue
            result[r.ClientCode] = ClientConfig(
                code=r.ClientCode,
                runtime_engine=runtime_engine,
                dialect=r.Dialect,
                octo_domain=octo_domain,
                octo_client_id=client_id,
                octo_secret=secret,
                octo_grant_type=grant_type,
                stats_engine=engines.get(r.StatsEngineKey),
                stats_dialect=r.StatsDialect or "tsql",
                docfields_engine=engines.get(r.DocfieldsEngineKey),
                docfields_dialect=r.DocfieldsDialect or "tsql",
            )
        # 'default' is guaranteed present regardless of the skip guard above or of
        # dbo.Clients missing/omitting the row -- pre-0079 the skip only ever
        # applied to MS02 (D5: preserve today's degradation verbatim), and
        # workitem_sources.py indexes CLIENTS["default"] unguarded.
        if "default" not in result:
            if default_skip_reason:
                logger.warning(
                    f"clients registry: active 'default' row skipped ({default_skip_reason}); "
                    "substituting hardcoded default"
                )
            result.update(_hardcoded_default())
        return result
    except Exception as e:
        # Record the degradation on the module BEFORE logging: this must not
        # depend on logging having been configured (it has not been, yet).
        REGISTRY_DEGRADED_REASON = f"{type(e).__name__}: {e}"
        logger.error(f"clients registry load: {e}")
        return _hardcoded_default()
    finally:
        if conn:
            conn.close()


CLIENTS = _build_clients()


def octo_creds_for_domain(domain):
    """Resolve (client_id, secret, grant_type) for the client owning ``domain``.

    Falls back to the default client's creds for an unknown domain so existing
    single-client behaviour is unchanged.
    """
    for c in CLIENTS.values():
        if c.octo_domain and c.octo_domain == domain:
            return c.octo_client_id, c.octo_secret, c.octo_grant_type
    return cfg.OCTO_CLIENT_ID, cfg.OCTO_CLIENT_SECRET, cfg.OCTO_GRANT_TYPE


def non_default_clients():
    """Active clients other than 'default', in registration order."""
    return [c for code, c in CLIENTS.items() if code != "default"]
