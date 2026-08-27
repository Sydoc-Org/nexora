"""Process- and client-name helpers shared between dashboard and workitems.

Most permissions are scoped by ``<client>.<process>`` (e.g. ``Privera.Invoices``)
so these helpers translate permission strings into SQL parameter lists.
"""

from flask import current_app, session

from . import mapping_config
from .db import engine_nexora_db
from .extensions import cache
from .security import has_permission


def _selected_pairs(prefix, process_name):
    """Granted (client, process) pairs for a comma-joined selection."""
    pairs = set()
    for name in process_name.split(","):
        name = name.strip()
        parts = name.split(".")
        if len(parts) >= 2 and has_permission(f"{prefix}{name}"):
            pairs.add((parts[0], parts[1]))
    return sorted(pairs)


def normalize_process_selection(process_name, allowed_processes):
    """Canonicalize a process-filter value against what the caller may see.

    Accepts the multi-select wire format (issue #150): ``"all"`` or a
    comma-joined ``"<client>.<process>"`` list. Returns
    ``(canonical_value, target_processes)``. Entries the caller holds no grant
    for are dropped, and a selection that ends up empty -- stale bookmark,
    forged arg, every box unticked -- falls back to ``"all"``, the historical
    single-select behaviour. Both halves are sorted so cache keys built from
    the canonical value stay stable regardless of click order.
    """
    allowed = sorted(allowed_processes)
    picked = sorted({p.strip() for p in (process_name or "").split(",")} & set(allowed))
    if not picked or picked == allowed:
        return "all", allowed
    return ",".join(picked), picked


def prepare_process_selection_sql(prefix, process_name):
    """Build an OR-joined parameterized (client, process) pair predicate --
    e.g. "(client = ? AND process = ?) OR (client = ? AND process = ?)" --
    plus its flat params list, from the caller's granted
    "<prefix><client>.<process>" permissions.

    ``process_name`` is "all" or a comma-joined list of "<client>.<process>"
    (issue #150); each entry is permission-checked on its own.

    Building two INDEPENDENT client/process IN-lists (the previous shape of
    this function) authorizes their full cross product once spliced into a
    query: a caller granted only (A, P1) and (B, P2) would also be
    authorized for (A, P2) and (B, P1), neither of which was ever granted.
    """
    try:
        perms = session.get("permissions", [])
        pairs = []
        if process_name == "all":
            unique_pairs = set()
            for perm in perms:
                if perm.startswith(prefix):
                    parts = perm.split(".")
                    client = parts[-2]
                    proc = parts[-1]
                    unique_pairs.add((client, proc))
            pairs = sorted(unique_pairs)
        else:
            pairs = _selected_pairs(prefix, process_name)
        predicate = " OR ".join("(client = ? AND process = ?)" for _ in pairs)
        params = [value for pair in pairs for value in pair]
        return params, predicate
    except Exception as e:
        current_app.logger.error(f"Failed to prepare process selection: {e}")
        raise


def prepare_process_selection_lists(prefix, process_name):
    """Like prepare_process_selection_sql but returns the granted (client,
    process) pairs as a plain list of tuples (no placeholder strings, no SQL
    text) — for the multi-source WorkitemFilter, which builds its own
    per-dialect OR-joined pair predicate from them.

    Returning independently-uniqued client and process lists (the previous
    shape) let a caller granted only (A, P1) and (B, P2) also read (A, P2)
    and (B, P1) -- the full client x process cross product -- once those two
    lists were spliced into independent IN-lists downstream.
    """
    try:
        perms = session.get("permissions", [])
        pairs = []
        if process_name == "all":
            unique_pairs = set()
            for perm in perms:
                if perm.startswith(prefix):
                    parts = perm.split(".")
                    unique_pairs.add((parts[-2], parts[-1]))
            pairs = sorted(unique_pairs)
        else:
            pairs = _selected_pairs(prefix, process_name)
        return pairs
    except Exception as e:
        current_app.logger.error(f"Failed to prepare process selection lists: {e}")
        raise


def get_activity_instances_to_ignore():
    """(client, process) -> frozenset of ActivityInstanceName values to hide
    from the workitem list for that process only. ``ProcessName`` in
    ActivityInstancesToIgnore is a ``<client>.<process>`` compound string, same
    convention as everywhere else in this module -- a rule configured for one
    process must never hide a differently-named activity on another process.
    """
    cached = cache.get("activity_instances_ignore")
    if cached is not None:
        return cached
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ProcessName, ActivityInstanceName FROM ActivityInstancesToIgnore")
        rows = cursor.fetchall()
        grouped = {}
        for row in rows:
            if "." not in row.ProcessName:
                continue
            parts = row.ProcessName.split(".")
            key = (parts[0], parts[-1])
            grouped.setdefault(key, set()).add(row.ActivityInstanceName)
        result = {key: frozenset(names) for key, names in grouped.items()}
        cache.set("activity_instances_ignore", result, timeout=3600)
        return result
    except Exception as e:
        current_app.logger.error(f"Failed to load activity instances to ignore: {e}")
        return {}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_params_from_process_list(process_list):
    proc_params = sorted({p.split(".")[-1] for p in process_list if "." in p})
    cli_params = sorted({p.split(".")[0] for p in process_list if "." in p})
    return (
        proc_params + cli_params,
        ", ".join(["?"] * len(proc_params)),
        ", ".join(["?"] * len(cli_params)),
    )


def build_stat_query(proc):
    """(TableName, ExportColumn, additionalCondition) for ``proc``, from the
    mapping_config registry (#98) -- successor to the direct Statconfig
    cursor read. No caller currently depends on a registry load failure
    surfacing as an exception (build_stat_query has no in-app callers as of
    #98 -- only tests/README reference it), so this stays a thin pass-through:
    ``sources_for`` degrades to ``[]`` on failure, same as the legacy
    except-block returning ``None``."""
    sources = mapping_config.sources_for(client=None, processes=[proc])
    if not sources:
        return None
    src = sources[0]
    return (src.table, src.export_column, src.extra_condition)
