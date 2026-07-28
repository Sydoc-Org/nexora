"""Process- and client-name helpers shared between dashboard and workitems.

Most permissions are scoped by ``<client>.<process>`` (e.g. ``Privera.Invoices``)
so these helpers translate permission strings into SQL parameter lists.
"""

from flask import current_app, session

from .db import engine_nexora_db
from .extensions import cache
from .security import has_permission


def prepare_process_selection_sql(prefix, process_name):
    """Build an OR-joined parameterized (client, process) pair predicate --
    e.g. "(client = ? AND process = ?) OR (client = ? AND process = ?)" --
    plus its flat params list, from the caller's granted
    "<prefix><client>.<process>" permissions.

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
            if has_permission(f"{prefix}{process_name}"):
                parts = process_name.split(".")
                if len(parts) >= 2:
                    pairs = [(parts[0], parts[1])]
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
            if has_permission(f"{prefix}{process_name}"):
                parts = process_name.split(".")
                if len(parts) >= 2:
                    pairs = [(parts[0], parts[1])]
        return pairs
    except Exception as e:
        current_app.logger.error(f"Failed to prepare process selection lists: {e}")
        raise


def get_activity_instances_to_ignore():
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
        result = ", ".join("'" + row.ActivityInstanceName.replace("'", "''") + "'" for row in rows)
        cache.set("activity_instances_ignore", result, timeout=3600)
        return result
    except Exception as e:
        current_app.logger.error(f"Failed to load activity instances to ignore: {e}")
        return ""
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
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        query = "SELECT TableName, ExportColumn, additionalCondition FROM Statconfig WHERE ProcessName = ?"
        cursor.execute(query, proc)
        return cursor.fetchone()
    except Exception as e:
        current_app.logger.error(f"Failed to build stat query for process {proc}: {e}")
        return None
    finally:
        if conn:
            conn.close()
        if cursor:
            cursor.close()
