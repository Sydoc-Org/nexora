"""Single cached accessor for the doc-field / process mapping config (#98).

Loads dbo.ProcessSources / ProcessFieldMappings / FieldLabels / FieldAliases
(migration 0074) into one frozen registry. Replaces ~30 hand-rolled SELECTs
against the legacy SearchConfig/Statconfig/IndexFieldMappings/
Search_Field_Labels tables.

Failure contract (inherited from the legacy helpers, do not weaken):
- a load error returns None from registry() and is NEVER cached (a cached
  empty fallback once disabled doc-field search app-wide for an hour);
- callers that historically failed OPEN behind session permissions coerce
  None to an empty value themselves (valid_field_keys, field_aliases);
- the external API keeps failing CLOSED on None (field_keys_for_processes,
  sensitive_field_keys).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from flask import current_app

from .db import engine_nexora_db
from .extensions import cache

_CACHE_KEY = "mapping_config_registry"
_TTL = 60  # seconds; admin-UI edits (phase 4) should apply fast


@dataclass(frozen=True)
class ProcessSource:
    client: str
    process: str
    table: str | None
    alias: str | None
    join_condition: str | None
    time_filter: str | None
    suggestion_time_filter: str | None
    export_column: str | None
    import_column: str | None
    workitem_column: str | None
    extra_condition: str | None
    id_column_type: str | None


@dataclass(frozen=True)
class FieldMapping:
    client: str
    process: str
    field_key: str
    column: str
    column_type: str | None


@dataclass(frozen=True)
class MappingRegistry:
    sources: dict[tuple[str, str], ProcessSource]
    mappings: list[FieldMapping]
    labels: dict[str, dict]
    aliases: dict[str, str]


def registry() -> MappingRegistry | None:
    """Cached (60s) registry of the four 0074 tables. None on load failure,
    never cached. An empty-but-successfully-loaded registry IS a valid
    success and gets cached."""
    reg: MappingRegistry | None = cache.get(_CACHE_KEY)
    if reg is not None:
        return reg
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT ClientCode, ProcessName, TableName, TableAlias, JoinCondition, "
            "TimeFilter, SuggestionTimeFilter, ExportColumn, ImportColumn, "
            "WorkitemColumn, ExtraCondition, IdColumnType FROM ProcessSources"
        )
        sources = {
            (r.ClientCode, r.ProcessName): ProcessSource(
                client=r.ClientCode,
                process=r.ProcessName,
                table=r.TableName,
                alias=r.TableAlias,
                join_condition=r.JoinCondition,
                time_filter=r.TimeFilter,
                suggestion_time_filter=r.SuggestionTimeFilter,
                export_column=r.ExportColumn,
                import_column=r.ImportColumn,
                workitem_column=r.WorkitemColumn,
                extra_condition=r.ExtraCondition,
                id_column_type=r.IdColumnType,
            )
            for r in cur.fetchall()
        }

        cur.execute(
            "SELECT ClientCode, ProcessName, FieldKey, ColumnName, ColumnType "
            "FROM ProcessFieldMappings"
        )
        mappings = [
            FieldMapping(
                client=r.ClientCode,
                process=r.ProcessName,
                field_key=r.FieldKey.lower(),
                column=r.ColumnName,
                column_type=r.ColumnType,
            )
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, "
            "IsSensitive FROM FieldLabels"
        )
        labels = {
            r.FieldKey.lower(): {
                "en": r.EnglishLabel,
                "de": r.GermanLabel,
                "fr": r.FrenchLabel,
                "it": r.ItalianLabel,
                "sensitive": bool(r.IsSensitive),
            }
            for r in cur.fetchall()
        }

        cur.execute("SELECT SourceFieldName, TargetKey FROM FieldAliases")
        aliases = {r.SourceFieldName: r.TargetKey.lower() for r in cur.fetchall()}

        reg = MappingRegistry(sources=sources, mappings=mappings, labels=labels, aliases=aliases)
        cache.set(_CACHE_KEY, reg, timeout=_TTL)  # success-only, including empty results
        return reg
    except Exception as e:
        current_app.logger.error(f"mapping_config load: {e}")
        return None
    finally:
        if conn:
            conn.close()


def invalidate_mapping_config() -> None:
    """Drop the cached registry so the next registry() call re-queries."""
    cache.delete(_CACHE_KEY)


def valid_field_keys() -> set[str]:
    """All known field keys. {} on failure (legacy get_valid_search_columns -> [])."""
    reg = registry()
    if reg is None:
        return set()
    return {m.field_key for m in reg.mappings}


def field_keys_for_processes(processes: Iterable[str]) -> set[str] | None:
    """Field keys available to the given processes.

    ``processes`` is an iterable of bare process names, compared directly
    against each mapping's ``m.process`` (matching ``mappings_for``'s
    convention -- NOT a ``"client.process"`` compound string). None on
    failure -- the external API surface fails CLOSED on None rather than
    falling back to an unrestricted or empty set.
    """
    reg = registry()
    if reg is None:
        return None
    wanted = set(processes)
    keys = set()
    for m in reg.mappings:
        if m.process in wanted:
            keys.add(m.field_key)
    return keys


def sensitive_field_keys() -> set[str] | None:
    """Field keys flagged sensitive in FieldLabels. None on failure (fails closed)."""
    reg = registry()
    if reg is None:
        return None
    return {key for key, meta in reg.labels.items() if meta["sensitive"]}


def labels() -> dict[str, dict] | None:
    """field_key -> {"en","de","fr","it","sensitive"}. None on failure.

    Returns a defensive copy (including per-field dicts) so a caller can
    never mutate the shared cached registry instance.
    """
    reg = registry()
    if reg is None:
        return None
    return {key: dict(meta) for key, meta in reg.labels.items()}


def field_aliases() -> dict[str, str]:
    """SourceFieldName -> TargetKey. {} on failure (legacy get_index_field_mappings -> {})."""
    reg = registry()
    if reg is None:
        return {}
    return dict(reg.aliases)


def sources_for(client: str | None, processes: Iterable[str] | None = None) -> list[ProcessSource]:
    """ProcessSource rows for ``client``, optionally restricted to ``processes``.

    ``client=None`` skips the client filter and returns sources across every
    client (nx_lib/views/dashboard.py's Statconfig-parity read, which then
    re-splits the combined list by ``.client`` -- see its
    ``_split_stat_configs``)."""
    reg = registry()
    if reg is None:
        return []
    wanted = set(processes) if processes is not None else None
    return [
        src
        for (src_client, src_process), src in reg.sources.items()
        if (client is None or src_client == client) and (wanted is None or src_process in wanted)
    ]


def mappings_for(
    client: str,
    processes: Iterable[str] | None = None,
    field_keys: Iterable[str] | None = None,
) -> list[FieldMapping]:
    """FieldMapping rows for ``client``, optionally restricted to ``processes``
    (None means all processes for that client), and optionally further
    restricted to ``field_keys`` (matched case-insensitively)."""
    reg = registry()
    if reg is None:
        return []
    wanted_processes = set(processes) if processes is not None else None
    wanted_fields = {k.lower() for k in field_keys} if field_keys is not None else None
    return [
        m
        for m in reg.mappings
        if m.client == client
        and (wanted_processes is None or m.process in wanted_processes)
        and (wanted_fields is None or m.field_key in wanted_fields)
    ]
