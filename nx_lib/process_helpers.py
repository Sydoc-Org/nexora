"""Process- and client-name helpers shared between dashboard and workitems.

Most permissions are scoped by ``<client>.<process>`` (e.g. ``Privera.Invoices``)
so these helpers translate permission strings into SQL parameter lists.
"""

from flask import current_app, session

from .db import engine_nexora_db
from .extensions import cache
from .security import has_permission


def prepare_process_selection_sql(prefix, process_name):
    try:
        perms = session.get("permissions", [])
        process_params = []
        client_params = []
        if process_name == "all":
            unique_processes = set()
            unique_clients = set()
            for perm in perms:
                if perm.startswith(prefix):
                    parts = perm.split(".")
                    client = parts[-2]
                    proc = parts[-1]

                    unique_clients.add(client)
                    unique_processes.add(proc)
            process_params = sorted(list(unique_processes))
            client_params = sorted(list(unique_clients))
        else:
            if has_permission(f"{prefix}{process_name}"):
                parts = process_name.split(".")
                if len(parts) >= 2:
                    client_params = [parts[0]]
                    process_params = [parts[1]]
        process_placeholders = ", ".join(["?"] * len(process_params))
        client_placeholders = ", ".join(["?"] * len(client_params))
        params = process_params + client_params
        return params, process_placeholders, client_placeholders
    except Exception as e:
        current_app.logger.error(f"Failed to prepare process selection: {e}")
        raise


def prepare_process_selection_lists(prefix, process_name):
    """Like prepare_process_selection_sql but returns (process_params, client_params)
    as separate lists (no placeholder strings) — for the multi-source WorkitemFilter."""
    try:
        perms = session.get("permissions", [])
        process_params = []
        client_params = []
        if process_name == "all":
            unique_processes = set()
            unique_clients = set()
            for perm in perms:
                if perm.startswith(prefix):
                    parts = perm.split(".")
                    unique_clients.add(parts[-2])
                    unique_processes.add(parts[-1])
            process_params = sorted(unique_processes)
            client_params = sorted(unique_clients)
        else:
            if has_permission(f"{prefix}{process_name}"):
                parts = process_name.split(".")
                if len(parts) >= 2:
                    client_params = [parts[0]]
                    process_params = [parts[1]]
        return process_params, client_params
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
        result = ", ".join("'" + row.ActivityInstanceName + "'" for row in rows)
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
