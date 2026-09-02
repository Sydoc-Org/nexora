"""Sync tenant `documents` entities into dbo.ReportingSources (K6).

``sync_tenant_reporting_sources()`` walks the tenant registry
(``nx_lib/tenant/registry.py``, Task 2) and, for every ``Kind='documents'``
``TenantEntity``, upserts one curated ``dbo.ReportingSources`` row so the
reporting builder's generic ``'table'`` provider can read it -- one box, one
source, no bespoke reporting code per tenant (mirrors the hand-seeded
``generali_pdqm`` / ``workitems`` rows from migration 0011, just written by
code instead of by a migration).

**T-SQL only (K6 deferral):** the curated ``'table'`` provider
(``nx_lib/reporting/table_query.py``) only ever emits T-SQL, and
``nx_lib/views/reporting.py``'s ``_CURATED_ENGINES`` only maps T-SQL engine
objects to a source's ``Engine`` column. An entity whose resolved dialect
isn't ``'tsql'``, or whose resolved engine object doesn't match one of
``_CURATED_ENGINES``' four engines, is skipped with a logged notice --
never partially registered. MS02 (the pilot tenant, Postgres) is skipped
this way for every one of its entities: teaching the curated provider the PG
dialect is real work, deferred to a later sub-project once the owner
green-lights it (spec K6). Until then MS02's data lives on its own tenant
pages only, not in the reporting builder.

Idempotent: each row is MERGEd on ``Code`` (`UQ_ReportingSources_Code`
backs this), mirroring the repo's proven MERGE exemplar
(``nx_lib/workitem_sources.py``'s ``_cache_store`` / ``nx_lib/prepared_documents.py``'s
``upsert_prepared_documents``) -- a re-run updates the existing row rather
than duplicating it.

No caller in the kernel itself (this task is tested in isolation): a later
sub-project's admin UI calls this alongside ``provision_tenant_permissions``
when a runtime tenant is created (spec K7/K6).
"""

import contextlib
import json

from flask import current_app

from ..clients import CLIENTS
from ..db import engine_generali_db, engine_nexora_db, engine_octo_db, engine_statistics_db
from .registry import fields_for, registry

# Mirrors nx_lib/views/reporting.py's _CURATED_ENGINES verbatim (same four
# imported engine objects, matched by identity) -- duplicated here rather than
# imported from that views module so this lib module never depends on the
# views layer. Keep this in lockstep with _CURATED_ENGINES if that dict's
# engines ever change.
_CURATED_ENGINE_KEYS = (
    (engine_nexora_db, "nexora"),
    (engine_statistics_db, "statistics"),
    (engine_generali_db, "generali"),
    (engine_octo_db, "octopus"),
)

# TenantField.semantic_role -> ColumnsJSON "type"; anything else (text,
# category, person, identifier, flag, ...) falls back to "string", the same
# default table_source_catalog() applies when "type" is omitted.
_SEMANTIC_TYPE = {
    "date": "date",
    "money": "number",
    "count": "number",
}

_MERGE_SQL = (
    "MERGE dbo.ReportingSources AS tgt "
    "USING (SELECT ? AS Code) AS src ON tgt.Code = src.Code "
    "WHEN MATCHED THEN UPDATE SET "
    "  Kind = ?, Label = ?, Permission = ?, Engine = ?, Provider = ?, BaseObject = ?, "
    "  ColumnsJSON = ?, Enabled = ?, SortOrder = ?, UpdatedAt = SYSUTCDATETIME() "
    "WHEN NOT MATCHED THEN INSERT "
    "  (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder) "
    "  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
)


def _engine_for_role(client, role):
    """Same role -> engine mapping as nx_lib/views/tenant.py's
    ``_engine_for_role`` (that module's private helper, so duplicated here
    rather than imported -- a lib module importing a views module would run
    the wrong way against the repo's layering)."""
    if role == "stats":
        return client.stats_engine
    if role == "docfields":
        return client.docfields_engine
    return client.runtime_engine


def _dialect_for_role(client, role):
    """Same role -> dialect mapping as nx_lib/views/tenant.py's
    ``_dialect_for_role`` -- see ``_engine_for_role``'s docstring."""
    if role == "stats":
        return client.stats_dialect
    if role == "docfields":
        return client.docfields_dialect
    return client.dialect


def _curated_engine_key(engine):
    """The `_CURATED_ENGINES` key for `engine` (by identity), or None when
    `engine` doesn't match any of the four curated engines (None included --
    an unavailable role engine degrades to None like every other engine in
    this codebase)."""
    for candidate, key in _CURATED_ENGINE_KEYS:
        if engine is candidate:
            return key
    return None


def _columns_json(tenant_code, entity_key):
    """ColumnsJSON text built from this entity's *visible* TenantFields only,
    in registry sort order -- shape matches table_source_catalog()'s input
    (nx_lib/reporting/table_query.py) so the curated 'table' provider reads
    it unchanged."""
    columns = [
        {
            "field": f.column,
            "label": f.labels.get("en") or f.column,
            "type": _SEMANTIC_TYPE.get(f.semantic_role, "string"),
            "filterable": True,
            "sortable": True,
        }
        for f in fields_for(tenant_code, entity_key)
        if f.visible
    ]
    return json.dumps(columns, ensure_ascii=False)


def sync_tenant_reporting_sources():
    """Upsert one curated dbo.ReportingSources row per T-SQL `documents`
    tenant entity; log-and-skip every entity whose engine doesn't resolve to
    a `_CURATED_ENGINES` key (postgres dialect, an unresolvable client, or an
    engine object that doesn't match one of the four curated engines).

    Returns ``{"synced": int, "skipped": int}``. Never raises: a registry
    load failure or a DB error is logged and answered with zero/partial
    counts rather than propagating, matching this codebase's degrade-not-500
    contract for background/admin-triggered sync jobs.
    """
    reg = registry()
    if reg is None:
        current_app.logger.error("sync_tenant_reporting_sources: tenant registry unavailable")
        return {"synced": 0, "skipped": 0}

    candidates = []
    skipped = 0
    for entity in reg.entities.values():
        if entity.kind != "documents":
            continue
        t = reg.tenants.get(entity.tenant)
        if t is None:
            current_app.logger.info(
                f"sync_tenant_reporting_sources: skipping {entity.tenant}/{entity.key} -- "
                "no active Tenant row"
            )
            skipped += 1
            continue
        client = CLIENTS.get(t.client_code)
        if client is None:
            current_app.logger.info(
                f"sync_tenant_reporting_sources: skipping {entity.tenant}/{entity.key} -- "
                f"no ClientConfig for client_code={t.client_code!r}"
            )
            skipped += 1
            continue
        dialect = _dialect_for_role(client, entity.engine_role)
        if dialect != "tsql":
            current_app.logger.info(
                f"sync_tenant_reporting_sources: skipping {entity.tenant}/{entity.key} -- "
                f"dialect {dialect!r} is not tsql (curated 'table' provider is T-SQL-only, K6)"
            )
            skipped += 1
            continue
        engine_key = _curated_engine_key(_engine_for_role(client, entity.engine_role))
        if engine_key is None:
            current_app.logger.info(
                f"sync_tenant_reporting_sources: skipping {entity.tenant}/{entity.key} -- "
                "engine does not map to a _CURATED_ENGINES key"
            )
            skipped += 1
            continue
        candidates.append((entity, t, engine_key))

    if not candidates:
        return {"synced": 0, "skipped": skipped}

    synced = 0
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        for entity, t, engine_key in candidates:
            code = f"tenant_{entity.tenant}_{entity.key}"
            label = f"{t.display_name} — {entity.labels.get('en') or entity.key}"
            permission = f"tenant.{entity.tenant}.view"
            columns_json = _columns_json(entity.tenant, entity.key)
            values = [
                "curated",
                label,
                permission,
                engine_key,
                "table",
                entity.source_object,
                columns_json,
                1,
                entity.sort_order,
            ]
            cur.execute(_MERGE_SQL, [code, *values, code, *values])
            synced += 1
        conn.commit()
        return {"synced": synced, "skipped": skipped}
    except Exception as e:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.rollback()
        current_app.logger.error(f"sync_tenant_reporting_sources: {e}")
        return {"synced": synced, "skipped": skipped}
    finally:
        if conn is not None:
            conn.close()
