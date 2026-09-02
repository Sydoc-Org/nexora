"""Data access for the MS02 'prepared documents' register (dbo.PreparedDocuments).

A thin, unit-testable seam over NexoraDB so the persistent register's I/O does
not live inside the multi-thousand-line workitems view. MS02-only at the call
sites (the routes gate on ms02_active); this module is purely about the table.

Insert vs update is classified by a pre-SELECT existence check per PID, then a
MERGE keyed on PID. This mirrors the repo's proven MERGE exemplar
(workitem_sources._cache_store), which uses neither OUTPUT $action nor a
post-fetch -- relying on OUTPUT $action + fetchone() is unverified against this
repo's pyodbc / SQL Server setup, whereas a SELECT + MERGE is driver-safe.
"""

import contextlib

from flask import current_app

from .db import engine_nexora_db


def upsert_prepared_documents(rows, uploaded_by):
    """Upsert each parsed row into dbo.PreparedDocuments, keyed on PID.

    rows: list[dict] with keys pid/collected/collected_by/prepared/prepared_by.
    uploaded_by: int | None (the acting user's id, an audit stamp).

    Per row: a SELECT classifies insert vs update, then a MERGE on PID applies
    the values (UPDATE sets UpdatedAt; INSERT sets UploadedBy/UploadedAt via the
    column default). Returns {"inserted": int, "updated": int, "total": int}.
    Raises RuntimeError on any DB failure (after rollback) so the caller can
    return a clear error without partially corrupting the register (a single
    failed row aborts the whole batch before commit).
    """
    merge_sql = (
        "MERGE dbo.PreparedDocuments AS tgt "
        "USING (SELECT ? AS PID) AS src ON tgt.PID = src.PID "
        "WHEN MATCHED THEN UPDATE SET "
        "  Collected = ?, CollectedBy = ?, Prepared = ?, PreparedBy = ?, "
        "  UploadedBy = ?, UpdatedAt = SYSUTCDATETIME() "
        "WHEN NOT MATCHED THEN INSERT "
        "  (PID, Collected, CollectedBy, Prepared, PreparedBy, UploadedBy) "
        "  VALUES (?, ?, ?, ?, ?, ?);"
    )
    inserted = 0
    updated = 0
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        for row in rows:
            pid = str(row.get("pid") or "").strip()
            if not pid:
                continue
            collected = 1 if row.get("collected") else 0
            collected_by = (row.get("collected_by") or "") or None
            prepared = 1 if row.get("prepared") else 0
            prepared_by = (row.get("prepared_by") or "") or None
            cur.execute("SELECT 1 FROM dbo.PreparedDocuments WHERE PID = ?", [pid])
            exists = cur.fetchone() is not None
            cur.execute(
                merge_sql,
                [
                    pid,
                    collected,
                    collected_by,
                    prepared,
                    prepared_by,
                    uploaded_by,
                    pid,
                    collected,
                    collected_by,
                    prepared,
                    prepared_by,
                    uploaded_by,
                ],
            )
            if exists:
                updated += 1
            else:
                inserted += 1
        conn.commit()
        return {"inserted": inserted, "updated": updated, "total": inserted + updated}
    except Exception as e:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.rollback()
        current_app.logger.error(f"upsert_prepared_documents: {e}")
        raise RuntimeError("prepared documents upsert failed") from e
    finally:
        if conn is not None:
            conn.close()


# Columns a caller may filter/group by. Fixed allowlist -- never interpolate
# caller-provided column names into SQL.
GROUP_BY_COLUMNS = {
    "collected_by": "CollectedBy",
    "prepared_by": "PreparedBy",
}


def _filter_clause(pid, collected, prepared):
    """Build a shared WHERE clause + params for count/fetch (kept in lockstep
    so the pagination total always matches what fetch actually returns)."""
    clauses = []
    params: list = []
    if pid:
        clauses.append("PID = ?")
        params.append(str(pid))
    if collected is not None:
        clauses.append("Collected = ?")
        params.append(1 if collected else 0)
    if prepared is not None:
        clauses.append("Prepared = ?")
        params.append(1 if prepared else 0)
    where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
    return where, params


def count_prepared_documents(pid=None, collected=None, prepared=None):
    """Total row count of the register (for pagination). Optional exact PID
    filter and Collected/Prepared boolean filters (None = don't filter)."""
    where, params = _filter_clause(pid, collected, prepared)
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM dbo.PreparedDocuments {where}", params)
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        if conn is not None:
            conn.close()


def fetch_prepared_documents_page(
    offset, limit, pid=None, collected=None, prepared=None, group_by=None
):
    """Return one OFFSET/FETCH page of the register.
    Optional exact PID filter (for the reverse ?pid deep-link), Collected/
    Prepared boolean filters, and group_by (a key of GROUP_BY_COLUMNS -- rows
    are ordered by that column so same-valued rows cluster together, newest
    first within each group). Default order is newest id first.

    Returns list[dict] with keys id/pid/collected/collected_by/prepared/
    prepared_by/uploaded_by/uploaded_at/updated_at.
    """
    where, params = _filter_clause(pid, collected, prepared)
    order_col = GROUP_BY_COLUMNS.get(group_by)
    order_by = f"{order_col} ASC, ID DESC" if order_col else "ID DESC"
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        base = (
            "SELECT ID, PID, Collected, CollectedBy, Prepared, PreparedBy, "
            "       UploadedBy, UploadedAt, UpdatedAt "
            "FROM dbo.PreparedDocuments "
            f"{where}"
            f"ORDER BY {order_by} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )
        params = [*params, int(offset), int(limit)]
        cur.execute(base, params)
        out = []
        for r in cur.fetchall():
            out.append(
                {
                    "id": r[0],
                    "pid": str(r[1]) if r[1] is not None else "",
                    "collected": bool(r[2]),
                    "collected_by": r[3] or "",
                    "prepared": bool(r[4]),
                    "prepared_by": r[5] or "",
                    "uploaded_by": r[6],
                    "uploaded_at": str(r[7]) if r[7] is not None else None,
                    "updated_at": str(r[8]) if r[8] is not None else None,
                }
            )
        return out
    finally:
        if conn is not None:
            conn.close()


def clear_prepared_documents():
    """Delete every row in the register. Returns the number of rows removed."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.PreparedDocuments")
        deleted = cur.rowcount
        conn.commit()
        return int(deleted) if deleted is not None and deleted >= 0 else 0
    finally:
        if conn is not None:
            conn.close()


def pids_in_register(pids):
    """Return the subset of `pids` present in dbo.PreparedDocuments.

    One parameterized SELECT (PID IN (...)). Empty input -> empty set without a DB
    round-trip. Never raises into the request: on any DB error it logs and returns an
    empty set (the reverse chip just won't show)."""
    wanted = [str(p) for p in (pids or []) if str(p).strip()]
    if not wanted:
        return set()
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        placeholders = ",".join(["?"] * len(wanted))
        cur.execute(
            f"SELECT PID FROM dbo.PreparedDocuments WHERE PID IN ({placeholders})",
            wanted,
        )
        return {str(r[0]) for r in cur.fetchall() if r[0] is not None}
    except Exception as e:
        current_app.logger.error(f"pids_in_register: {e}")
        return set()
    finally:
        if conn is not None:
            conn.close()
