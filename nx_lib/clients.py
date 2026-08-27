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
    engines = {
        "engine_octo_db": engine_octo_db,
        "engine_statistics_db": engine_statistics_db,
        "engine_ms02_pg": engine_ms02_pg,
        "engine_ms02_stats_pg": engine_ms02_stats_pg,
        "engine_ms02_docfields_pg": engine_ms02_docfields_pg,
    }

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
        for r in rows:
            if not r.IsActive:
                continue
            runtime_engine = engines.get(r.RuntimeEngineKey)
            env_domain, client_id, secret, grant_type = _creds_for(r.SecretRef)
            octo_domain = r.OctoDomain or env_domain
            if runtime_engine is None or not octo_domain:
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
            result.update(_hardcoded_default())
        return result
    except Exception as e:
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
