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
from dataclasses import dataclass, replace

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
    """A branded portal: the organizations whose ``Organizations.TenantCode``
    points here share its navigation group. Where data lives is not a tenant
    property -- each entity carries its own ``client_code`` (0096)."""

    code: str
    display_name: str
    active: bool


@dataclass(frozen=True)
class TenantEntity:
    tenant: str
    key: str
    source_object: str
    client_code: str  # the dbo.Clients row whose engine holds source_object (0096)
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

        cur.execute("SELECT TenantCode, DisplayName, IsActive FROM Tenants WHERE IsActive = 1")
        tenants = {
            r.TenantCode: Tenant(
                code=r.TenantCode,
                display_name=r.DisplayName,
                active=bool(r.IsActive),
            )
            for r in cur.fetchall()
        }

        cur.execute(
            "SELECT TenantCode, EntityKey, SourceObject, ClientCode, Kind, EngineRole, IdColumn, "
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
                client_code=r.ClientCode,
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
    cache.delete(_ORG_CACHE_KEY)


_ORG_CACHE_KEY = "tenant_org_map"


def organization_tenant(org_code: str | None) -> str | None:
    """TenantCode of the organization ``org_code`` belongs to (0090,
    ``Organizations.TenantCode``), or None -- also None when the map cannot be
    loaded (fail closed = the user is treated as *not* tenant-scoped and keeps
    the global navigation, never the other way round). Same 60 s cache as the
    registry; a failed load is never cached."""
    if not org_code:
        return None
    m = organization_tenant_map()
    return m.get(org_code) if m is not None else None


def organization_tenant_map() -> dict[str, str] | None:
    """{organizationcode: TenantCode} for every organization inside a tenant
    (``Organizations.TenantCode``), cached 60 s. None when the map cannot be
    loaded -- never cached, callers fail closed."""
    m: dict[str, str] | None = cache.get(_ORG_CACHE_KEY)
    if m is not None:
        return m
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT organizationcode, TenantCode FROM Organizations WHERE TenantCode IS NOT NULL"
        )
        m = {r.organizationcode: r.TenantCode for r in cur.fetchall()}
        cache.set(_ORG_CACHE_KEY, m, timeout=_TTL)
        return m
    except Exception as e:
        current_app.logger.error(f"tenant_org_map load: {e}")
        return None
    finally:
        if conn:
            conn.close()


def processes_of_tenant(sources, org_to_tenant: dict[str, str], code: str) -> set[str]:
    """Process names (``ProcessSources.ProcessName``) of the sources whose
    organization belongs to tenant ``code``. Pure: ``sources`` are objects with
    ``.process`` / ``.organization`` (mapping_config's ProcessSource)."""
    return {
        s.process
        for s in sources
        if getattr(s, "organization", None) and org_to_tenant.get(s.organization) == code
    }


def tenant_processes(code: str) -> set[str] | None:
    """The processes that belong to tenant ``code`` (0097: the tenant-scoped
    dashboard narrows a user's process grants to this set). None when either
    registry is unavailable -- the caller treats that as *no* processes, never
    as *all*."""
    from .. import mapping_config  # local: mapping_config is a sibling leaf module

    reg = mapping_config.registry()
    m = organization_tenant_map()
    if reg is None or m is None:
        return None
    return processes_of_tenant(reg.sources.values(), m, code)


def tenant(code: str) -> Tenant | None:
    """The active Tenant for ``code``. None on failure or unknown/inactive code."""
    reg = registry()
    if reg is None:
        return None
    return reg.tenants.get(code)


def pages_for(code: str) -> list[TenantPage]:
    """Active TenantPage rows for ``code``, ordered by SortOrder. [] on failure.

    Returns pages with a defensive copy of ``layout`` (same reasoning as
    entity_for/fields_for below) so a caller can never mutate the shared
    cached registry instance.
    """
    reg = registry()
    if reg is None:
        return []
    pages = sorted((p for p in reg.pages if p.tenant == code), key=lambda p: p.sort_order)
    return [replace(p, layout=dict(p.layout) if p.layout is not None else None) for p in pages]


def entity_for(code: str, entity_key: str) -> TenantEntity | None:
    """The active TenantEntity for (tenant, entity_key). None on failure or not found.

    ``cache`` is Flask-Caching's in-process SimpleCache -- cache.get() hands
    back the exact object cache.set() stored, no serialization boundary in
    between. ``frozen=True`` blocks attribute reassignment but not in-place
    mutation of a dict *field*, so returning ``.labels`` by reference would
    let a caller corrupt the shared cache entry for every tenant, for up to
    _TTL seconds. Return a defensive copy of ``labels`` instead (mirrors
    mapping_config.labels()'s per-field dict copy).
    """
    reg = registry()
    if reg is None:
        return None
    e = reg.entities.get((code, entity_key))
    if e is None:
        return None
    return replace(e, labels=dict(e.labels))


def fields_for(code: str, entity_key: str) -> list[TenantField]:
    """Active TenantField rows for (tenant, entity_key), ordered by SortOrder. [] on failure.

    Returns fields with a defensive copy of ``labels`` (see entity_for's
    docstring) so a caller can never mutate the shared cached registry
    instance.
    """
    reg = registry()
    if reg is None:
        return []
    fields = sorted(
        (f for f in reg.fields if f.tenant == code and f.entity == entity_key),
        key=lambda f: f.sort_order,
    )
    return [replace(f, labels=dict(f.labels)) for f in fields]


def provision_tenant_permissions(cursor, code: str) -> None:
    """Idempotently insert the ``tenant.<code>.view`` / ``tenant.<code>.edit``
    rows into dbo.Permission -- granted to nobody; granting happens at
    /admin/access-control (K7: the kernel only ever has one tenant to create,
    by migration, so this is exposed for sub-project 2's future admin UI to
    reuse rather than being wired into a route itself).

    Mirrors the idempotent
    ``INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p
    WHERE p.Code = ?)`` shape ``nx_lib/views/admin/processes.py``'s
    ``api_admin_process_source_add`` uses for its own dbo.Permission row --
    same table, same guard, so a second call (or a re-run of the same seed
    migration) is a no-op rather than a duplicate-key error.

    Takes a cursor, not a connection: like the process-source insert it
    mirrors, this only executes the two INSERTs -- committing (and owning the
    surrounding transaction) is the caller's responsibility.
    """
    for suffix, description in (
        ("view", f"View {code} tenant records"),
        ("edit", f"Edit {code} tenant records"),
    ):
        perm_code = f"tenant.{code}.{suffix}"
        cursor.execute(
            "INSERT INTO dbo.Permission (Code, Description) SELECT ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = ?)",
            (perm_code, description[:200], perm_code),
        )
