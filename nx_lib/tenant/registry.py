"""Single cached accessor for the tenant/data-box registry (tenant-kernel).

Loads dbo.Tenants / TenantEntities / TenantFields / TenantPages (migration
0084) into one frozen registry. This is the structural twin of
nx_lib/mapping_config.py -- same cache, same TTL, same failure contract.

Failure contract (inherited from mapping_config, do not weaken):
- a load error returns None from registry() and is NEVER cached;
- an empty-but-successfully-loaded registry IS a valid success and gets
  cached;
- callers derived from registry() (tenant/pages_for/entity_for/fields_for)
  fail CLOSED -- None or an empty list/dict, never a partial/unsafe result.

Every SELECT is filtered to Status = 'active' at load time (Tenants has no
Status column, only IsActive). SourceObject / IdColumn / ColumnName are
identifier-shape validated at load time against _IDENT_RE -- a row that
fails validation is dropped and logged, so nothing downstream (query
builders, admin writes) ever sees an unvalidated identifier.
"""

import json
import re
from dataclasses import dataclass

from flask import current_app

from ..db import engine_nexora_db
from ..extensions import cache

_CACHE_KEY = "tenant_config_registry"
_TTL = 60  # seconds

# Identifier-shaped values only: a leading letter/underscore, then letters,
# digits, underscore, dot, or bracket/quote (schema-qualified, quoted, or
# bracketed identifiers), capped at 100 chars. Reused by Task 3 (query
# builder) and the sub-project-2 admin writes -- keep this the single source
# of truth for "is this string safe to interpolate as an identifier".
_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_."\[\]]{0,99}$')


@dataclass(frozen=True)
class Tenant:
    code: str
    display_name: str
    organization_code: str
    client_code: str
    active: bool


@dataclass(frozen=True)
class TenantEntity:
    tenant: str
    key: str
    source_object: str
    kind: str
    engine_role: str
    id_column: str
    labels: dict
    sort_order: int


@dataclass(frozen=True)
class TenantField:
    tenant: str
    entity: str
    column: str
    semantic_role: str
    lookup_entity: str | None
    labels: dict
    visible: bool
    sort_order: int


@dataclass(frozen=True)
class TenantPage:
    tenant: str
    key: str
    page_type: str
    entity: str | None
    layout: dict | None
    sort_order: int


@dataclass(frozen=True)
class TenantRegistry:
    tenants: dict[str, Tenant]
    entities: dict[tuple[str, str], TenantEntity]
    fields: list[TenantField]
    pages: list[TenantPage]


def registry() -> TenantRegistry | None:
    """Cached (60s) registry of the four tenant tables (active rows only).

    None on load failure, never cached. An empty-but-successfully-loaded
    registry IS a valid success and gets cached.
    """
    reg: TenantRegistry | None = cache.get(_CACHE_KEY)
    if reg is not None:
        return reg
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT TenantCode, DisplayName, OrganizationCode, ClientCode, IsActive "
            "FROM Tenants WHERE IsActive = 1"
        )
        tenants = {
            r.TenantCode: Tenant(
                code=r.TenantCode,
                display_name=r.DisplayName,
                organization_code=r.OrganizationCode,
                client_code=r.ClientCode,
                active=bool(r.IsActive),
            )
            for r in cur.fetchall()
        }

        cur.execute(
            "SELECT TenantCode, EntityKey, SourceObject, Kind, EngineRole, IdColumn, "
            "LabelEn, LabelDe, LabelFr, LabelIt, SortOrder FROM TenantEntities "
            "WHERE Status = 'active'"
        )
        entities = {}
        for r in cur.fetchall():
            if not _IDENT_RE.match(r.SourceObject) or not _IDENT_RE.match(r.IdColumn):
                current_app.logger.error(
                    f"tenant_config load: dropping TenantEntities row "
                    f"{r.TenantCode}/{r.EntityKey} -- unsafe identifier "
                    f"(SourceObject={r.SourceObject!r}, IdColumn={r.IdColumn!r})"
                )
                continue
            entities[(r.TenantCode, r.EntityKey)] = TenantEntity(
                tenant=r.TenantCode,
                key=r.EntityKey,
                source_object=r.SourceObject,
                kind=r.Kind,
                engine_role=r.EngineRole,
                id_column=r.IdColumn,
                labels={"en": r.LabelEn, "de": r.LabelDe, "fr": r.LabelFr, "it": r.LabelIt},
                sort_order=r.SortOrder,
            )

        cur.execute(
            "SELECT TenantCode, EntityKey, ColumnName, SemanticRole, LookupEntity, "
            "LabelEn, LabelDe, LabelFr, LabelIt, IsVisible, SortOrder FROM TenantFields "
            "WHERE Status = 'active'"
        )
        fields = []
        for r in cur.fetchall():
            if not _IDENT_RE.match(r.ColumnName):
                current_app.logger.error(
                    f"tenant_config load: dropping TenantFields row "
                    f"{r.TenantCode}/{r.EntityKey}/{r.ColumnName} -- unsafe identifier "
                    f"(ColumnName={r.ColumnName!r})"
                )
                continue
            fields.append(
                TenantField(
                    tenant=r.TenantCode,
                    entity=r.EntityKey,
                    column=r.ColumnName,
                    semantic_role=r.SemanticRole,
                    lookup_entity=r.LookupEntity,
                    labels={"en": r.LabelEn, "de": r.LabelDe, "fr": r.LabelFr, "it": r.LabelIt},
                    visible=bool(r.IsVisible),
                    sort_order=r.SortOrder,
                )
            )

        cur.execute(
            "SELECT TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder "
            "FROM TenantPages WHERE Status = 'active'"
        )
        pages = []
        for r in cur.fetchall():
            layout = None
            if r.LayoutJSON:
                try:
                    layout = json.loads(r.LayoutJSON)
                except (TypeError, ValueError) as e:
                    current_app.logger.error(
                        f"tenant_config load: TenantPages {r.TenantCode}/{r.PageKey} "
                        f"LayoutJSON parse error: {e}"
                    )
                    layout = None
            pages.append(
                TenantPage(
                    tenant=r.TenantCode,
                    key=r.PageKey,
                    page_type=r.PageType,
                    entity=r.EntityKey,
                    layout=layout,
                    sort_order=r.SortOrder,
                )
            )

        reg = TenantRegistry(tenants=tenants, entities=entities, fields=fields, pages=pages)
        cache.set(_CACHE_KEY, reg, timeout=_TTL)  # success-only, including empty results
        return reg
    except Exception as e:
        current_app.logger.error(f"tenant_config load: {e}")
        return None
    finally:
        if conn:
            conn.close()


def invalidate_tenant_config() -> None:
    """Drop the cached registry so the next registry() call re-queries."""
    cache.delete(_CACHE_KEY)


def tenant(code: str) -> Tenant | None:
    """The active Tenant for ``code``. None on failure or unknown/inactive code."""
    reg = registry()
    if reg is None:
        return None
    return reg.tenants.get(code)


def pages_for(code: str) -> list[TenantPage]:
    """Active TenantPage rows for ``code``, ordered by SortOrder. [] on failure."""
    reg = registry()
    if reg is None:
        return []
    return sorted((p for p in reg.pages if p.tenant == code), key=lambda p: p.sort_order)


def entity_for(code: str, entity_key: str) -> TenantEntity | None:
    """The active TenantEntity for (tenant, entity_key). None on failure or not found."""
    reg = registry()
    if reg is None:
        return None
    return reg.entities.get((code, entity_key))


def fields_for(code: str, entity_key: str) -> list[TenantField]:
    """Active TenantField rows for (tenant, entity_key), ordered by SortOrder. [] on failure."""
    reg = registry()
    if reg is None:
        return []
    return sorted(
        (f for f in reg.fields if f.tenant == code and f.entity == entity_key),
        key=lambda f: f.sort_order,
    )
