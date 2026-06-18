"""Client registry: maps each tenant to its runtime DB engine + Octo creds.

Module graph (no cycles): clients -> config, db. octo and workitem_sources
import clients; clients imports neither.
"""

from dataclasses import dataclass

from . import config as cfg
from .db import (
    engine_ms02_docfields_pg,
    engine_ms02_pg,
    engine_ms02_stats_pg,
    engine_octo_db,
    engine_statistics_db,
)


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


def _build_clients():
    clients = {
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
    # MS02 is registered only when both its engine and Octo domain are present.
    if engine_ms02_pg is not None and cfg.MS02_OCTO_DOMAIN:
        clients["ms02"] = ClientConfig(
            code="ms02",
            runtime_engine=engine_ms02_pg,
            dialect="postgres",
            octo_domain=cfg.MS02_OCTO_DOMAIN,
            octo_client_id=cfg.MS02_OCTO_CLIENT_ID,
            octo_secret=cfg.MS02_OCTO_CLIENT_SECRET,
            octo_grant_type=cfg.MS02_OCTO_GRANT_TYPE,
            stats_engine=engine_ms02_stats_pg,
            stats_dialect="postgres",
            docfields_engine=engine_ms02_docfields_pg,
            docfields_dialect="postgres",
        )
    return clients


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
