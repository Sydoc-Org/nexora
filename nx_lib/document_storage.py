"""Client document-storage databases (issue #398): the engines behind
``nx_lib/workitems/tables.py``, resolved from the client registry.

Octo keeps each client's documents in a storage named in the runtime's
``t_DocumentStorages``. Its connection string there is encrypted for Octo's
own use; nexora does not need it -- **by convention (owner decision
2026-09-28) the storage is a database of the same name on the client's
runtime server**, and the ``<Default>`` entry is the runtime database
itself. That holds on INT and PROD today (``EM_Storage``,
``Compass_Storage``, ``Privera_*_Storage``, ... next to ``RuntimeDatabase``;
MS02's ``Documentstorage`` next to its Postgres ``RuntimeDatabase``), and the
app's runtime login can already read every one of them. Nothing is renamed
and nothing is configured; ``nx --doctor`` verifies that every storage the
runtime lists can actually be opened.

Module graph (no cycles): document_storage -> clients, db, workitems.tables.
"""

import re
import threading

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from . import db
from .clients import CLIENTS
from .workitems import tables as _tables

# A storage name is interpolated into a connection string as a database
# name -- accept only plain identifiers (the rows are Octo-managed, never
# user input, but the guard costs nothing).
_STORAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")

_engines: dict[tuple[str, str], object] = {}
_lock = threading.Lock()


def runtime_for(client_code):
    """``(engine, dialect)`` of a registered client's runtime DB, or None."""
    client = CLIENTS.get(client_code)
    if client is None:
        return None
    return client.runtime_engine, "postgres" if client.dialect == "postgres" else "tsql"


def storage_engine_for(client_code, storage_name):
    """Engine for one document storage of a client. ``<Default>`` (or no
    name) is the runtime engine; any other name is a sibling database on the
    runtime server, created once and cached for the process lifetime (small
    pool -- one API call reads a storage in a single pass)."""
    client = CLIENTS.get(client_code)
    if client is None:
        raise RuntimeError(f"document storage: unknown client {client_code!r}")
    if not storage_name or storage_name == _tables.DEFAULT_STORAGE_NAME:
        return client.runtime_engine
    if not _STORAGE_NAME_RE.match(storage_name):
        raise RuntimeError(f"document storage: refusing storage name {storage_name!r}")
    key = (client_code, storage_name)
    with _lock:
        engine = _engines.get(key)
        if engine is None:
            url: str | URL
            if client.dialect == "postgres":
                url = client.runtime_engine.url.set(database=storage_name)
            else:
                url = db.get_db_url(storage_name)
            engine = create_engine(
                url,
                pool_size=2,
                max_overflow=8,
                pool_timeout=30,
                pool_recycle=1800,
                pool_pre_ping=True,
            )
            _engines[key] = engine
    return engine


def list_storages(client_code="default"):
    """``[storage_name, ...]`` the client's runtime lists (for ``nx --doctor``).
    Raises on a DB failure."""
    runtime = runtime_for(client_code)
    if runtime is None:
        return []
    engine, dialect = runtime
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        if dialect == "postgres":
            cur.execute('SELECT "Name" FROM "t_DocumentStorages" ORDER BY "ID"')
        else:
            cur.execute("SELECT Name FROM t_DocumentStorages ORDER BY ID")
        names = [row[0] for row in cur.fetchall() if row[0]]
        cur.close()
        return names
    finally:
        conn.close()


def fetch_workitem_tables(ids_by_client, logger=None):
    """Production binding of :func:`nx_lib.workitems.tables.fetch_workitem_tables`."""
    return _tables.fetch_workitem_tables(
        ids_by_client,
        runtime_for=runtime_for,
        storage_for=storage_engine_for,
        logger=logger,
    )
