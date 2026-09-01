"""Tenant kernel: the cached data-box registry over dbo.Tenants /
TenantEntities / TenantFields / TenantPages (migration 0084).

Re-exports the public registry contract consumed by later tasks (routes,
query builders, nav, reporting sync).
"""

from .registry import (
    _IDENT_RE,
    Tenant,
    TenantEntity,
    TenantField,
    TenantPage,
    TenantRegistry,
    entity_for,
    fields_for,
    invalidate_tenant_config,
    pages_for,
    registry,
    tenant,
)

__all__ = [
    "_IDENT_RE",
    "Tenant",
    "TenantEntity",
    "TenantField",
    "TenantPage",
    "TenantRegistry",
    "entity_for",
    "fields_for",
    "invalidate_tenant_config",
    "pages_for",
    "registry",
    "tenant",
]
