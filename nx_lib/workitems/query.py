"""Workitems list-query engine extracted from ``nx_lib/views/workitems.py``.
Pure Python: no Flask, no ``session``/``request``/``current_app``. Every
piece of session/permission-derived state (the ``scope`` dict) and every
external dependency this needs (DB engines, the resolver/merge-page
callables, the cache, a logger) is passed in explicitly by the Flask-aware
caller in ``nx_lib/views/workitems.py`` (D4). Moved LAST within the package:
it is built on top of ``fields``/``sensitivity``/``media`` below.
"""

import math
import re
from datetime import datetime

from .. import mapping_config
from ..config import DB_STATISTICS
from ..process_helpers import normalize_process_selection
from ..workitem_sources import _MS02_IDENT, WorkitemFilter, _ms02_id_column
from . import fields as fields_dsl

# The 'ms02' ProcessFieldMappings field key whose column value is the
# personal-number (PID) EAV "Name" in the MS02 doc-field index. Owner-seeded.
_MS02_PID_SEARCH_FIELD = "pid"


def ms02_pid_specs(target_processes):
    """Columnar specs for resolving personal numbers (PIDs) against the MS02
    statistik table: ``[(table, id_col, pid_col, time_filter, pid_column_type,
    id_column_type), ...]`` read from the 'ms02' ProcessFieldMappings 'pid'
    rows for the given processes (mapping_config registry, ClientCode='ms02',
    ProcessName IN (target_processes) -- NEVER a hardcoded process key).
    ``time_filter`` is None: the PID lookup is an exact match that must
    surface ALL matching workitems, unbounded by time.

    ``pid_column_type`` (FieldMapping.column_type, #98 Task 12) types the
    ``pid_col = ANY(%s)`` comparisons in resolve_ms02_pid_ids /
    resolve_ms02_pid_to_wids; ``id_column_type`` (ProcessSource.id_column_type)
    types the DIFFERENT ``id_col = ANY(%s)`` comparison in
    resolve_ms02_wids_to_pids -- deliberately two separate type fields since
    they describe two different columns. Returns [] when unseeded."""
    if not target_processes:
        return []
    mappings = mapping_config.mappings_for(
        "ms02", target_processes, field_keys={_MS02_PID_SEARCH_FIELD}
    )
    if not mappings:
        return []
    sources = {s.process: s for s in mapping_config.sources_for("ms02", target_processes)}
    specs = []
    for m in mappings:
        src = sources.get(m.process)
        if src is None or not src.table or not m.column:
            continue
        id_col = _ms02_id_column(src.join_condition, src.alias)
        if not id_col:
            continue
        specs.append((src.table, id_col, m.column, None, m.column_type, src.id_column_type))
    return specs


def ms02_prepared_docs_processes():
    """The MS02 processes for which the Prepared Documents register is relevant:
    the 'ms02' ProcessFieldMappings rows that carry a 'pid' mapping (single
    source of truth, NEVER a hardcoded process key -- currently just
    ['sydoc.05_PDBS']). The Workitems toolbar link is gated to these processes.
    Returns [] when unseeded or on error so the caller degrades to hiding the
    link."""
    mappings = mapping_config.mappings_for("ms02", None, field_keys={_MS02_PID_SEARCH_FIELD})
    return sorted({m.process for m in mappings if m.process})


def get_workitems_data(
    args,
    scope,
    *,
    export_all,
    valid_db_columns,
    activity_ignore_map,
    engine_statistics_db,
    engine_ms02_docfields_pg,
    resolve_ms02_docfield_ids,
    fetch_merged_page,
    cache,
    logger,
    export_max_rows,
    workitem_stages,
):
    """The workitems-list query engine: resolves filters (including the two
    doc-field pre-resolution legs, #98) into a ``WorkitemFilter`` and returns
    the merged page.

    Every session/permission read the interactive UI needs is pre-resolved
    into ``scope`` by the caller's ``_session_scope()``; the external API
    builds its own scope from the caller's API key instead (same keys, no
    session) -- this function itself never touches ``session``/``request``.
    Every collaborator that would otherwise be a Flask-context global
    (DB engines, the MS02 resolver, ``fetch_merged_page``, the cache, the
    app logger) is passed in explicitly so this module stays Flask-free (D4).

    Returns the same ``{"workitems", "pagination", "degradedSources"}`` shape
    as before, PLUS a ``"process_name"`` key (the resolved process-selection
    string) for the caller to persist to session -- this function itself never
    writes to session. The caller is also responsible for MS02 pid/
    in_register row-stamping (``_stamp_in_register``), which stays in
    views/workitems.py (it is itself Flask/session-coupled)."""
    page = args.get("page", 1, type=int)
    search_term = args.get("search", "").strip()
    status = args.get("status", "")
    stage = args.get("stage", "")
    start_date_str = args.get("startDate", "")
    end_date_str = args.get("endDate", "")
    start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
    end_date = datetime.fromisoformat(end_date_str) if end_date_str else None
    if export_all:
        per_page = export_max_rows
        offset = 0
    else:
        per_page = int(args.get("perPage", 40))
        if per_page not in (40, 100, 200, 500, 1000):
            per_page = 40
        offset = (page - 1) * per_page

    allowed_processes_set = scope["allowed"]

    # "all" or a comma-joined selection (issue #150).
    process_name, target_processes = normalize_process_selection(
        args.get("prcfW", "all"), allowed_processes_set
    )

    # target_processes is already the selection intersected with the allowed
    # set (normalize_process_selection), so the (client, process) pairs derive
    # from it directly -- equivalent to the former session-reading
    # prepare_process_selection_lists call, but scope-driven.
    client_process_pairs = sorted(
        {(p.split(".")[0], p.split(".")[-1]) for p in target_processes if "." in p}
    )

    docfields = args.getlist("docfield")
    docvalues = args.getlist("docvalue")
    docops = args.getlist("docop")
    doccombs = args.getlist("doccomb")

    # Doc-field search is pre-resolved (against SearchConfig -> StatisticsDB) into
    # a single intersected id allow-set for the SQL Server source. None = no
    # constraint; empty set = force no rows; populated = twi.ID IN (...).
    docfield_ids = None
    ms02_docfield_ids = None

    if scope["can_docfields"] and target_processes:
        blocked_docfields = scope["sensitive_blocked"]

        # One registry read per leg (#98 phase-3 perf) instead of one SearchConfig
        # query per pair: mapping_config.registry() is cached in-process, so this
        # is zero NexoraDB round-trips on a warm cache, vs. len(docfields) before.
        default_mappings = mapping_config.mappings_for("default", target_processes)
        default_sources = {
            s.process: s for s in mapping_config.sources_for("default", target_processes)
        }
        _default_id_col_cache = {}

        def _default_id_col(src):
            # Same JoinCondition/alias regex the legacy SearchConfig-row path
            # used, cached per (leg, process) rather than re-derived per pair.
            if src.process not in _default_id_col_cache:
                id_col = None
                for part in re.split(r"\s*=\s*", (src.join_condition or "").strip()):
                    if src.alias and re.match(
                        rf"^{re.escape(src.alias)}\.\w+$", part.strip(), re.IGNORECASE
                    ):
                        id_col = part.strip()
                        break
                if not id_col:
                    logger.warning(
                        f"Could not extract ID col from JoinCondition: {src.join_condition}"
                    )
                _default_id_col_cache[src.process] = id_col
            return _default_id_col_cache[src.process]

        # Result cache (#98 Task 13): key on the target processes plus the
        # pairs that actually drive resolution (sensitive-blocked/invalid
        # pairs already dropped by _docfield_pairs_normalized, so the key
        # itself is permission-scoped). ("v", result) sentinel distinguishes
        # a resolved-but-empty set from a cache miss.
        _default_pairs_normalized = fields_dsl._docfield_pairs_normalized(
            docfields, docvalues, docops, doccombs, valid_db_columns, blocked_docfields
        )
        _default_cache_key = fields_dsl._docfield_ids_cache_key(
            "default", target_processes, _default_pairs_normalized
        )
        _default_cached = cache.get(_default_cache_key)
        if (
            isinstance(_default_cached, tuple)
            and len(_default_cached) == 2
            and _default_cached[0] == "v"
        ):
            docfield_ids = _default_cached[1]
        else:
            _default_had_error = False
            try:
                for pair_idx, (docfield, docvalue) in enumerate(
                    zip(docfields, docvalues, strict=False)
                ):
                    docfield = (docfield or "").lower().strip()
                    docvalue = (docvalue or "").strip()

                    if not docvalue:
                        continue

                    if docfield:
                        if docfield not in valid_db_columns:
                            continue
                        if docfield in blocked_docfields:
                            continue
                        target_field_keys = {docfield}
                    else:
                        # Value-first search (issue #148): no field picked -> OR the
                        # value across every permitted, non-sensitive field. The
                        # UNION below already ORs across configs, so widening it to
                        # multiple fields keeps the same shape.
                        target_field_keys = {
                            c for c in valid_db_columns if c not in blocked_docfields
                        }
                        if not target_field_keys:
                            continue

                    op_key = fields_dsl._docfield_op(docops, pair_idx)

                    configs = [m for m in default_mappings if m.field_key in target_field_keys]

                    if not configs:
                        # Field unmapped for every targeted default process -> this
                        # pair cannot match here -> force zero rows for THIS pair.
                        # No early break (an OR-joined later pair may still widen
                        # the result); the fold below preserves AND semantics.
                        pair_ids = set()
                    else:
                        id_parts = []
                        id_params = []
                        for config in configs:
                            src = default_sources.get(config.process)
                            if src is None or not src.table:
                                continue
                            tbl = src.table
                            alias = src.alias
                            time_filter = src.time_filter

                            id_col = _default_id_col(src)
                            if not id_col:
                                continue

                            db_column = config.column
                            if not db_column:
                                continue
                            # Sargable predicate from ColumnType (#98 Task 12) --
                            # bare-column/native-int compare when the type is
                            # known-safe, else the legacy CAST+COLLATE fallback.
                            pred_sql, pred_params = fields_dsl._docfield_predicate(
                                alias, db_column, config.column_type, op_key, docvalue
                            )
                            id_parts.append(f"""
                                SELECT DISTINCT {id_col} AS id
                                FROM {tbl} {alias}
                                WHERE {pred_sql}
                                AND {time_filter}
                            """)
                            id_params.extend(pred_params)

                        if not id_parts:
                            continue  # mapping rows exist but unusable -> tolerant skip

                        stat_conn = None
                        try:
                            stat_conn = engine_statistics_db.raw_connection()
                            stat_cur = stat_conn.cursor()
                            union_sql = " UNION ALL ".join(id_parts)
                            stat_cur.execute(f"SELECT DISTINCT id FROM ({union_sql}) t", id_params)
                            matching_ids = [row[0] for row in stat_cur.fetchall()]
                        except Exception as e:
                            logger.error(f"Error pre-fetching docfield IDs: {e}")
                            matching_ids = None
                            _default_had_error = True
                        finally:
                            if stat_conn:
                                stat_conn.close()

                        # StatisticsDB error -> this pair cannot be checked. Fail
                        # CLOSED for the pair (empty set), never unconstrained.
                        pair_ids = set() if matching_ids is None else set(matching_ids)

                    comb = fields_dsl._docfield_comb(doccombs, pair_idx)
                    if docfield_ids is None:
                        docfield_ids = pair_ids
                    elif comb == "or":
                        docfield_ids = docfield_ids | pair_ids
                    else:
                        docfield_ids = docfield_ids & pair_ids

            except Exception as e:
                logger.error(f"Error in docfield pre-fetch block: {e}")
                _default_had_error = True

            # Never cache an error/None-path result (D7): a StatisticsDB
            # failure fails the PAIR closed (set()) without raising, so an
            # error flag -- not just "no exception" -- gates the write.
            if not _default_had_error:
                cache.set(_default_cache_key, ("v", docfield_ids), timeout=60)

    # --- MS02 columnar doc-field pre-resolution (sibling to the default block) ---
    # Resolves through the SAME SearchConfig mapping but against the separate
    # MS02 doc-field DB (wide per-process statistik tables). The default block
    # above (StatisticsDB -> docfield_ids) is a parallel, independent allow-set
    # so a mixed default+MS02 request never cross-shrinks. Guarded by the same
    # permission + target_processes; when the engine is absent this block is
    # skipped and the fail-closed guard below forces zero MS02 rows.
    if scope["can_docfields"] and target_processes and engine_ms02_docfields_pg is not None:
        blocked_docfields = scope["sensitive_blocked"]

        # One registry read per leg (#98 phase-3 perf), mirroring the default
        # leg above -- see its comment for the round-trip-elimination rationale.
        ms02_mappings = mapping_config.mappings_for("ms02", target_processes)
        ms02_sources = {s.process: s for s in mapping_config.sources_for("ms02", target_processes)}
        _ms02_id_col_cache = {}

        def _cached_ms02_id_col(src):
            if src.process not in _ms02_id_col_cache:
                _ms02_id_col_cache[src.process] = _ms02_id_column(src.join_condition, src.alias)
            return _ms02_id_col_cache[src.process]

        # Result cache (#98 Task 13) -- see the default leg above for the key
        # shape and the fail-closed rationale; identical treatment here.
        _ms02_pairs_normalized = fields_dsl._docfield_pairs_normalized(
            docfields, docvalues, docops, doccombs, valid_db_columns, blocked_docfields
        )
        _ms02_cache_key = fields_dsl._docfield_ids_cache_key(
            "ms02", target_processes, _ms02_pairs_normalized
        )
        _ms02_cached = cache.get(_ms02_cache_key)
        if isinstance(_ms02_cached, tuple) and len(_ms02_cached) == 2 and _ms02_cached[0] == "v":
            ms02_docfield_ids = _ms02_cached[1]
        else:
            _ms02_had_error = False
            try:
                pairs = []
                for pair_idx, (docfield, docvalue) in enumerate(
                    zip(docfields, docvalues, strict=False)
                ):
                    docfield = (docfield or "").lower().strip()
                    docvalue = (docvalue or "").strip()
                    if not docvalue:
                        continue
                    if docfield:
                        # Whitelist the field key (same guard the default path uses)
                        # before it drives a mapping_config lookup -- blocks an
                        # unknown/injected `docfield` from reaching the resolver.
                        if docfield not in valid_db_columns:
                            continue
                        if docfield in blocked_docfields:
                            continue
                        target_field_keys = {docfield}
                    else:
                        # Value-first search (issue #148): no field picked -> specs
                        # spanning every permitted field; the resolver ORs specs
                        # within a pair, so this is OR-across-fields for free.
                        target_field_keys = {
                            c for c in valid_db_columns if c not in blocked_docfields
                        }
                        if not target_field_keys:
                            continue

                    # Each matching FieldMapping maps a docfield to a COLUMN in a wide
                    # statistik table (column = the column name); build one columnar
                    # spec per mapping (specs within a pair are OR'd in the resolver).
                    config_rows = [m for m in ms02_mappings if m.field_key in target_field_keys]
                    if not config_rows:
                        # Field unmapped for every targeted ms02 process -> this
                        # pair cannot match here -> forced-empty pair (empty specs;
                        # the resolver folds it as set()). No early break (mirrors
                        # the default leg): an OR-joined later pair may still widen.
                        pairs.append(
                            (
                                [],
                                docvalue,
                                fields_dsl._docfield_op(docops, pair_idx),
                                fields_dsl._docfield_comb(doccombs, pair_idx),
                            )
                        )
                        continue
                    specs = []
                    for m in config_rows:
                        src = ms02_sources.get(m.process)
                        if src is None or not src.table:
                            continue
                        id_col = _cached_ms02_id_col(src)
                        if not id_col:
                            continue
                        field_col = m.column
                        if not field_col:
                            continue
                        # 5-tuple (#98 Task 12): field_type drives the typed
                        # int-eq fast path in resolve_ms02_docfield_ids.
                        specs.append((src.table, id_col, field_col, src.time_filter, m.column_type))
                    if not specs:
                        continue  # mapping rows exist but unusable -> tolerant no-constraint
                    pairs.append(
                        (
                            specs,
                            docvalue,
                            fields_dsl._docfield_op(docops, pair_idx),
                            fields_dsl._docfield_comb(doccombs, pair_idx),
                        )
                    )
                if pairs:
                    if any(entry[0] for entry in pairs):
                        ms02_docfield_ids = resolve_ms02_docfield_ids(
                            engine_ms02_docfields_pg, pairs
                        )
                        if ms02_docfield_ids is None:
                            # resolve_ms02_docfield_ids never raises -- it fails
                            # closed to None on error, so a None result here IS
                            # the error path (D7): must not be cached.
                            _ms02_had_error = True
                    else:
                        # Every active pair is unmapped for ms02 -> zero MS02 rows
                        # without a resolver round-trip (also keeps the "resolver
                        # must not run without mapping rows" contract).
                        ms02_docfield_ids = set()
            except Exception as e:
                logger.error(f"Error in MS02 docfield pre-fetch block: {e}")
                _ms02_had_error = True
                ms02_docfield_ids = None

            if not _ms02_had_error:
                cache.set(_ms02_cache_key, ("v", ms02_docfield_ids), timeout=60)

    # Fail CLOSED: an active doc-field search must never leave a source
    # unconstrained. Every unresolved path -- absent MS02 engine, resolver/DB
    # error, unusable mapping, unknown field key -- lands here as None and
    # becomes an empty allow-set (zero rows from that source) instead of "no
    # constraint" (which floods the result with the source's entire corpus;
    # observed on STAGING 2026-07-20). Sensitive-blocked fields keep their
    # designed "silently ignored" semantics and do not count as active.
    if scope["can_docfields"] and target_processes:
        _blocked = scope["sensitive_blocked"]
        # A pair is active when it has a value and either no field (value-first
        # any-field search) or a non-sensitive field.
        _active = any(
            (v or "").strip()
            and (not (f or "").strip() or (f or "").lower().strip() not in _blocked)
            for f, v in zip(docfields, docvalues, strict=False)
        )
        if _active:
            if docfield_ids is None:
                docfield_ids = set()
            if ms02_docfield_ids is None:
                ms02_docfield_ids = set()

    status_map = {"Ready": 0, "In Progress": 1, "Done": 5}
    # Soft-deleted workitems are hidden from every other view; asking for them by
    # name is the ONLY way to see them, and only for holders of the internal
    # permission. Without it "Deleted" maps to None -> the unfiltered query, which
    # still carries `Status <> 2`, so an unauthorized caller cannot reach them.
    if scope["can_deleted"]:
        status_map["Deleted"] = 2
    filt = WorkitemFilter(
        client_process_pairs=client_process_pairs,
        activity_ignore_map=activity_ignore_map,
        status_code=status_map.get(status) if (status and scope["can_status"]) else None,
        stage=stage if (stage in workitem_stages and scope["can_stage"]) else None,
        search_id=search_term if (search_term and scope["can_search_id"]) else None,
        start_date=start_date if (start_date and scope["can_dates"]) else None,
        end_date=end_date if (end_date and scope["can_dates"]) else None,
        docfields=docfields or [],  # raw pairs kept for autocomplete only
        docvalues=docvalues or [],
        docfield_ids=docfield_ids,  # StatisticsDB-resolved -> SqlServerSource only
        ms02_docfield_ids=ms02_docfield_ids,  # MS02 doc-field DB-resolved -> PostgresSource
    )
    rows, total_items, degraded = fetch_merged_page(filt, offset, per_page)
    workitems_list = rows

    total_pages = math.ceil(total_items / per_page) if per_page else 0
    return {
        "process_name": process_name,
        "workitems": workitems_list,
        "pagination": {
            "currentPage": page,
            "totalPages": total_pages,
            "totalItems": total_items,
            "perPage": per_page,
        },
        "degradedSources": degraded,
    }


def docfield_suggestions_any_field(
    target_processes,
    target_cols,
    *,
    engine_statistics_db,
    engine_ms02_docfields_pg,
    cache,
    logger,
    cache_timeout=600,
):
    """Pure core of the value-first mode of /api/docfield_values (issue #148):
    labeled suggestions ``[(value, field_key), ...]`` across every permitted,
    non-sensitive field (``target_cols``, already filtered by the caller),
    read from cache or resolved live against StatisticsDB (default leg) and
    the MS02 doc-field DB (ms02 leg). Callers turn this into the
    ``[{value, field}]`` JSON shape and apply the ``q`` substring filter.

    Per-source DB errors are caught and logged, never raised -- matching the
    historical behaviour of degrading to whatever the OTHER source returned
    rather than 500ing the whole suggestion list."""
    if not target_cols:
        return []

    # Cache key includes the column set: users with/without the sensitive-fields
    # perm must not share entries.
    cache_key = (
        f"docfield_vals_any_{'_'.join(sorted(target_processes))}_{'-'.join(sorted(target_cols))}"
    )
    pairs = cache.get(cache_key)
    if pairs is not None:
        return pairs

    default_mappings = mapping_config.mappings_for(
        "default", target_processes, field_keys=target_cols
    )
    default_sources = {
        s.process: s for s in mapping_config.sources_for("default", target_processes)
    }
    ms02_mappings = mapping_config.mappings_for("ms02", target_processes, field_keys=target_cols)
    ms02_sources = {s.process: s for s in mapping_config.sources_for("ms02", target_processes)}

    default_parts = []
    ms02_specs = []  # (table, column, field_key, suggestion_time_filter)
    for m in default_mappings:
        src = default_sources.get(m.process)
        if src is None or not src.table or not m.column:
            continue
        safe_col = f"CAST({m.column} AS NVARCHAR(MAX))"
        # m.field_key derives from the whitelisted mapping_config field
        # keys -- safe to inline as a literal.
        default_parts.append(f"""
            SELECT {safe_col} COLLATE DATABASE_DEFAULT AS Val, '{m.field_key}' AS FieldKey
            FROM [{DB_STATISTICS}].{src.table}
            WHERE {m.column} IS NOT NULL
              AND {safe_col} <> ''
              AND {src.suggestion_time_filter}
        """)
    for m in ms02_mappings:
        src = ms02_sources.get(m.process)
        if src is None or not src.table or not m.column:
            continue
        if _MS02_IDENT.match(m.column):
            ms02_specs.append((src.table, m.column, m.field_key, src.suggestion_time_filter))

    vals = set()
    if default_parts:
        stat_conn = None
        try:
            union_sql = " UNION ALL ".join(default_parts)
            stat_conn = engine_statistics_db.raw_connection()
            stat_cur = stat_conn.cursor()
            stat_cur.execute(
                f"SELECT DISTINCT TOP 500 Val, FieldKey FROM ({union_sql}) t ORDER BY Val"
            )
            vals.update((r[0], r[1]) for r in stat_cur.fetchall())
        except Exception as e:
            logger.error(f"/api/docfield_values any-field default error: {e}")
        finally:
            if stat_conn:
                stat_conn.close()

    if ms02_specs and engine_ms02_docfields_pg is not None:
        df_conn = None
        try:
            df_conn = engine_ms02_docfields_pg.raw_connection()
            df_cur = df_conn.cursor()
            for table, col, fkey, stf in ms02_specs:
                sql = (
                    f'SELECT DISTINCT "{col}"::text AS v FROM {table} '
                    f'WHERE "{col}"::text IS NOT NULL AND "{col}"::text <> %s'
                )
                if stf:
                    sql += f" AND {stf}"
                sql += " ORDER BY v LIMIT 500"
                df_cur.execute(sql, [""])
                vals.update((r[0], fkey) for r in df_cur.fetchall())
            df_cur.close()
        except Exception as e:
            logger.error(f"/api/docfield_values any-field ms02 error: {e}")
        finally:
            if df_conn:
                df_conn.close()

    pairs = sorted(vals)
    cache.set(cache_key, pairs, timeout=cache_timeout)
    return pairs
