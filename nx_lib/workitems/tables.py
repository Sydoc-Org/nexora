"""Table values of a page of workitems, read from the client's document
storage database (issue #398) -- the set-based twin of the per-workitem
Octo document-service fetch behind ``/api/v1/workitems/<id>``.

Pure Python: no Flask, no engines of its own. The caller injects two
resolvers (``nx_lib/document_storage.py`` is the production one):

- ``runtime_for(client)`` -> ``(engine, dialect)`` for the client's runtime
  DB (``t_WorkItems`` / ``t_DocumentStorages``), ``dialect`` in
  ``{"tsql", "postgres"}``;
- ``storage_for(client, storage_name)`` -> engine for the named document
  storage (``t_Documents`` / ``t_DocumentMedia``).

Where the data lives (verified on INT and PROD, 2026-09-28): the runtime
``t_DocumentStorages`` row names each client storage, and Octo keeps that
storage in a **separate database of the same name on the same server**
(``EM_Storage``, ``Compass_Storage``, ...); the ``<Default>`` entry is the
runtime database itself. Inside a storage, ``t_DocumentMedia`` holds one
plain-XML media item per document of the system media type
``SystemTableList`` (:data:`SYSTEM_TABLE_LIST_MEDIA_TYPE`): a
``ModelObjectList`` of ``STGTable`` elements -- ``TableName``,
``internalColumnDefinition`` and ``internalRows/item/internalCells/item``
cells carrying ``ColumnName``, ``CellValue/Text`` (``is-null="true"`` when
unset) and the raw ``CapturedValue``.

:func:`parse_table_list` applies the SAME reduction rules as
``nx_lib/table_locations.py`` does to the document service's JSON, so the
result is the shape ``_api_tables`` (nx_lib/views/api_external.py) serves on
the detail endpoint: a cell with no value is skipped, a row with no valued
cell is dropped, a table with no rows is dropped, and ``columns`` is the
first-seen order of valued cells' names. Container documents contribute
nothing themselves -- :func:`leaf_documents` descends to the leaves exactly
like ``field_locations.items_of`` does on the JSON tree. Checked against
the document service on 12/12 INT workitems (Compass, Elektromaterial,
Privera Invoice, RuntimeDatabase storages).

Cost: one runtime query to locate the page's root documents, then per
storage one query for the child documents per nesting level and one for
the table streams -- no per-workitem HTTP. Any DB failure raises: the
external API's page contract is strict (500, never a silently partial
page), same as ``fetch_docfield_values``.
"""

import xml.etree.ElementTree as ET  # nosec B405 -- XML comes from our own DB, not from a client

# t_MediaTypes.RowGuid of the system media type 'SystemTableList' -- the same
# GUID on every Octo runtime (SQL Server and the MS02 Postgres one alike).
SYSTEM_TABLE_LIST_MEDIA_TYPE = "CC4D139C-1004-4B7A-8CEF-68643F4F0A19"

# The t_DocumentStorages.Name that means "the runtime database itself" (no
# separate storage DB). A workitem with no storage row at all is treated the
# same way.
DEFAULT_STORAGE_NAME = "<Default>"

# Guard against a cyclic ParentDocumentID chain (never seen; belt and braces).
MAX_DOCUMENT_DEPTH = 8

# pyodbc caps a statement at 2100 parameters; 500 ids per IN list keeps the
# locate/children/stream queries well under it. Postgres takes one array.
_CHUNK = 500


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def _text_or_none(el):
    """Text of an STG value element, or None when it is absent or marked
    ``is-null="true"`` (an unset value -- distinct from an empty string,
    which the document service also reports as ``""``)."""
    if el is None or el.get("is-null") == "true":
        return None
    return el.text or ""


def _cell_value(cell):
    """Prefer ``CellValue/Text``, fall back to the raw ``CapturedValue`` --
    the same precedence as ``table_locations._cell_value``. None = empty."""
    value = _text_or_none(cell.find("./CellValue/Text"))
    if value is None:
        value = _text_or_none(cell.find("CapturedValue"))
    return value


def parse_table_list(data):
    """``SystemTableList`` XML (bytes or str, BOM tolerated) ->
    ``[{title, columns, rows: [[{column, value}, ...], ...]}, ...]`` -- one
    entry per non-empty table, the detail endpoint's ``tables`` shape.
    Empty input yields ``[]``; malformed XML raises (a corrupt stream is a
    backend failure, not an empty table)."""
    if isinstance(data, bytes | bytearray | memoryview):
        text = bytes(data).decode("utf-8-sig", "replace")
    else:
        text = (data or "").lstrip("﻿")
    text = text.strip()
    if not text:
        return []
    root = ET.fromstring(text)  # nosec B314 -- see module docstring
    out = []
    for tbl in root.iter("STGTable"):
        columns = []
        seen = set()
        rows_out = []
        for row in tbl.findall("./internalRows/item"):
            cells_out = []
            for cell in row.findall("./internalCells/item"):
                value = _cell_value(cell)
                if value is None:
                    continue
                col = cell.findtext("ColumnName")
                if col is not None and col not in seen:
                    seen.add(col)
                    columns.append(col)
                cells_out.append({"column": col, "value": value})
            if cells_out:
                rows_out.append(cells_out)
        if rows_out:
            out.append({"title": tbl.findtext("TableName"), "columns": columns, "rows": rows_out})
    return out


def leaf_documents(roots, children_of):
    """``{root_id: [leaf_id, ...]}`` -- a document with children is a
    container and contributes nothing itself; we descend, recursively, to the
    documents without children (pre-order, children sorted by id for a
    deterministic result). A leaf root maps to itself. Mirrors
    ``field_locations.items_of`` on the document-service tree."""

    def walk(doc, depth):
        kids = children_of.get(doc) or []
        if not kids or depth >= MAX_DOCUMENT_DEPTH:
            return [doc]
        out = []
        for kid in sorted(kids):
            out.extend(walk(kid, depth + 1))
        return out

    return {root: walk(root, 0) for root in roots}


def _norm_doc_id(value):
    """Document ids come back as ``str`` (pyodbc) or ``uuid.UUID`` (psycopg2)
    and in mixed case; compare and key them lowercased."""
    return str(value).lower() if value is not None else None


def _chunked(seq, size=_CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# --------------------------------------------------------------------------- #
# SQL legs (dialect-switched, raw DB-API cursors like workitem_sources.py)
# --------------------------------------------------------------------------- #


def _locate(engine, dialect, ids):
    """``[(workitem_id, root_doc_id, storage_name), ...]`` from the runtime
    DB. A workitem with no storage row (LEFT JOIN miss) gets the default
    storage; one with no root document is skipped (nothing to read)."""
    out = []
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        if dialect == "postgres":
            cur.execute(
                'SELECT twi."ID", twi."RootDocumentID"::text, s."Name" '
                'FROM "t_WorkItems" twi '
                'LEFT JOIN "t_DocumentStorages" s ON s."ID" = twi."DocumentStorageID" '
                'WHERE twi."ID" = ANY(%s)',
                [list(ids)],
            )
            rows = cur.fetchall()
        else:
            rows = []
            for chunk in _chunked(list(ids)):
                marks = ", ".join("?" * len(chunk))
                cur.execute(
                    "SELECT twi.ID, twi.RootDocumentID, s.Name "
                    "FROM t_WorkItems twi "
                    "LEFT JOIN t_DocumentStorages s ON s.ID = twi.DocumentStorageID "
                    f"WHERE twi.ID IN ({marks})",
                    list(chunk),
                )
                rows.extend(cur.fetchall())
        for wid, root, name in rows:
            root = _norm_doc_id(root)
            if root is None:
                continue
            out.append((wid, root, name or DEFAULT_STORAGE_NAME))
        cur.close()
    finally:
        conn.close()
    return out


def _children_of(engine, dialect, roots):
    """``{parent_id: [child_id, ...]}`` for the whole subtree under ``roots``
    -- one query per nesting level, until a level has no children."""
    children: dict[str | None, list[str]] = {}
    frontier = list(roots)
    depth = 0
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        while frontier and depth < MAX_DOCUMENT_DEPTH:
            found = []
            if dialect == "postgres":
                cur.execute(
                    'SELECT "ID"::text, "ParentDocumentID"::text FROM "t_Documents" '
                    'WHERE "ParentDocumentID" = ANY(%s::uuid[])',
                    [frontier],
                )
                found = cur.fetchall()
            else:
                for chunk in _chunked(frontier):
                    marks = ", ".join("?" * len(chunk))
                    cur.execute(
                        "SELECT ID, ParentDocumentID FROM t_Documents "
                        f"WHERE ParentDocumentID IN ({marks})",
                        list(chunk),
                    )
                    found.extend(cur.fetchall())
            frontier = []
            for child, parent in found:
                child, parent = _norm_doc_id(child), _norm_doc_id(parent)
                if child in children or child is None:
                    continue  # already visited (cycle guard)
                children.setdefault(parent, []).append(child)
                frontier.append(child)
            depth += 1
        cur.close()
    finally:
        conn.close()
    return children


def _table_streams(engine, dialect, doc_ids):
    """``{doc_id: xml_bytes}`` -- the SystemTableList media item of each
    document that has one."""
    out: dict[str | None, bytes] = {}
    if not doc_ids:
        return out
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        if dialect == "postgres":
            cur.execute(
                'SELECT "DocumentID"::text, "Data" FROM "t_DocumentMedia" '
                'WHERE "MediaTypeIdentifier" = %s::uuid AND "DocumentID" = ANY(%s::uuid[])',
                [SYSTEM_TABLE_LIST_MEDIA_TYPE, list(doc_ids)],
            )
            rows = cur.fetchall()
        else:
            rows = []
            for chunk in _chunked(list(doc_ids)):
                marks = ", ".join("?" * len(chunk))
                cur.execute(
                    "SELECT DocumentID, Data FROM t_DocumentMedia "
                    f"WHERE MediaTypeIdentifier = ? AND DocumentID IN ({marks})",
                    [SYSTEM_TABLE_LIST_MEDIA_TYPE, *chunk],
                )
                rows.extend(cur.fetchall())
        for doc_id, blob in rows:
            if blob is not None:
                out[_norm_doc_id(doc_id)] = bytes(blob)
        cur.close()
    finally:
        conn.close()
    return out


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def fetch_workitem_tables(ids_by_client, *, runtime_for, storage_for, logger=None):
    """``{(client, workitem_id): [table, ...]}`` for a page of workitems.

    ``ids_by_client`` is ``{client_code: [workitem_id, ...]}`` (workitem
    identity is compound). Every located workitem gets an entry, ``[]`` when
    its documents carry no populated table; a workitem the runtime does not
    know is simply absent. Raises on any DB failure (strict page contract).
    """
    out = {}
    for client, ids in ids_by_client.items():
        ids = [i for i in ids if i is not None]
        if not ids:
            continue
        runtime = runtime_for(client)
        if runtime is None:
            raise RuntimeError(f"workitem tables: no runtime engine for client {client!r}")
        engine, dialect = runtime
        by_storage: dict[str, list[tuple]] = {}
        for wid, root, storage in _locate(engine, dialect, ids):
            by_storage.setdefault(storage, []).append((wid, root))
        for storage, pairs in by_storage.items():
            store = storage_for(client, storage)
            roots = sorted({root for _, root in pairs})
            leaves = leaf_documents(roots, _children_of(store, dialect, roots))
            streams = _table_streams(
                store, dialect, sorted({leaf for ls in leaves.values() for leaf in ls})
            )
            for wid, root in pairs:
                tables = []
                for leaf in leaves[root]:
                    blob = streams.get(leaf)
                    if blob is not None:
                        tables.extend(parse_table_list(blob))
                out[(client, wid)] = tables
            if logger is not None:
                logger.debug(
                    f"workitem tables: {client}/{storage}: {len(pairs)} workitems, "
                    f"{len(streams)} table streams"
                )
    return out
