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


def count_prepared_documents():
    """Total row count of the register (for pagination)."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dbo.PreparedDocuments")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        if conn is not None:
            conn.close()


def fetch_prepared_documents_page(offset, limit):
    """Return one OFFSET/FETCH page of the register, newest id first.

    Returns list[dict] with keys id/pid/collected/collected_by/prepared/
    prepared_by/uploaded_by/uploaded_at/updated_at.
    """
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT ID, PID, Collected, CollectedBy, Prepared, PreparedBy, "
            "       UploadedBy, UploadedAt, UpdatedAt "
            "FROM dbo.PreparedDocuments "
            "ORDER BY ID DESC "
            "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
            [int(offset), int(limit)],
        )
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
