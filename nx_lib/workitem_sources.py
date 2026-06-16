"""Multi-source workitem runtime layer.

Each WorkitemSource wraps one runtime DB (SQL Server OctoDB or MS02 Postgres)
behind a uniform interface and emits the normalized row dict documented in the
plan. The merged-list endpoint fetches per source and merges in Python.

Module graph (no cycles): workitem_sources -> clients, db, config. It does NOT
import octo (document fetching stays in the views).
"""

import json
from dataclasses import dataclass, field

from flask import current_app

from . import config as cfg
from .clients import CLIENTS
from .db import engine_nexora_db

DB_NEXORA = cfg.DB_NEXORA


@dataclass
class WorkitemFilter:
    """Dialect-neutral bag of the list filters. Each source renders its own SQL."""

    process_names: list  # tp.Name allow-list (from permissions)
    client_names: list  # tp.ClientName allow-list (from permissions)
    activity_ignore_csv: str  # "'A','B'" string from ActivityInstancesToIgnore
    status_code: int | None = None
    search_id: str | None = None  # LIKE term (no % yet)
    start_date: object = None
    end_date: object = None
    priority: str | None = None
    assigned_user: str | None = None
    tag: str | None = None
    # Raw doc-field search pairs. Each source resolves them against its OWN stats
    # store (spec §4.6): SqlServerSource via SearchConfig->StatisticsDB (the
    # orchestrator pre-resolves those into `docfield_ids` below); PostgresSource
    # in-query against its own t_documentindexes (Name/Stringvalue).
    docfields: list = field(default_factory=list)
    docvalues: list = field(default_factory=list)
    # StatisticsDB-resolved id allow-set for the SQL SERVER source ONLY (default
    # client's stats store). PostgresSource ignores this and uses the raw pairs.
    docfield_ids: set | None = None


def merge_sorted_rows(row_lists):
    """Merge per-source normalized rows into one list, newest first.

    Deterministic tie-break on workitemid (ascending) so equal timestamps order
    stably across sources.
    """
    flat = [r for rows in row_lists for r in rows]
    flat.sort(key=lambda r: r["workitemid"])
    flat.sort(key=lambda r: r["modifiedat"], reverse=True)
    return flat


class SqlServerSource:
    """Default client: existing OctoDB query, lifted verbatim from
    nx_lib/views/workitems.py. Cross-DB joins to NexoraDB stay in-query."""

    code = "default"

    def __init__(self):
        self.engine = CLIENTS["default"].runtime_engine

    def has_workitem(self, workitem_id):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT TOP 1 1 FROM t_WorkItems WHERE ID = ?", workitem_id)
            return cur.fetchone() is not None
        except Exception as e:
            current_app.logger.error(f"SqlServerSource.has_workitem({workitem_id}): {e}")
            return False
        finally:
            conn.close()

    def list_workitems(self, filt, offset, limit):
        """Return (rows, total_count). Builds the same WHERE + SQL the original
        _get_workitems_data ran against engine_octo_db."""
        where_clauses = [
            f"tp.Name IN ({_qmarks(filt.process_names)})",
            f"tp.ClientName IN ({_qmarks(filt.client_names)})",
            "twi.Status <> 2",
            f"tai.ActivityInstanceName not in ({filt.activity_ignore_csv})",
        ]
        params = list(filt.process_names) + list(filt.client_names)

        if filt.status_code is not None:
            where_clauses.append("twi.Status = ?")
            params.append(filt.status_code)
        if filt.tag:
            where_clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                    JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                    WHERE wt.workitemid = twi.id AND t.TagName like ?
                )
            """
            )
            params.append(f"%{filt.tag}%")
        if filt.search_id:
            where_clauses.append("twi.id LIKE ?")
            params.append(f"%{filt.search_id}%")
        if filt.start_date:
            where_clauses.append("twi.ModifiedAt >= ?")
            params.append(filt.start_date)
        if filt.end_date:
            where_clauses.append("twi.ModifiedAt < ?")
            params.append(filt.end_date)
        if filt.priority:
            where_clauses.append("ISNULL(wim.Priority, 0) = ?")
            params.append(filt.priority)
        if filt.assigned_user:
            if filt.assigned_user in ("None", "Unassigned"):
                where_clauses.append("(wim.AssignedUserID IS NULL)")
            else:
                where_clauses.append("wim.AssignedUserID = ?")
                params.append(filt.assigned_user)

        extra_clauses = []
        temp_tables = []
        if filt.docfield_ids is not None:
            ids = list(filt.docfield_ids)
            if not ids:
                extra_clauses.append("1=0")
            elif len(ids) > 500:
                temp_tables.append(("#docf0", ids))
                extra_clauses.append("twi.ID IN (SELECT id FROM #docf0)")
            else:
                extra_clauses.append(f"twi.ID IN ({_qmarks(ids)})")
                params.extend(ids)

        full_where = " AND ".join(where_clauses + extra_clauses)

        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor()
            for temp_name, ids in temp_tables:
                cur.execute(f"CREATE TABLE {temp_name} (id NVARCHAR(255))")
                for i in range(0, len(ids), 1000):
                    batch = ids[i : i + 1000]
                    cur.execute(
                        f"INSERT INTO {temp_name}(id) VALUES {','.join(['(?)'] * len(batch))}",
                        batch,
                    )

            cur.execute(
                f"""
                SELECT COUNT(twi.ID)
                FROM t_WorkItems twi
                INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.workitemid
                WHERE {full_where}
            """,
                params,
            )
            total = cur.fetchone()[0] or 0

            cur.execute(
                f"""
                WITH WorkitemCTE AS (
                    SELECT
                        twi.ModifiedAt, twi.ID AS WorkItemID,
                        CASE
                            WHEN twi.Status = 0 THEN 'Ready' WHEN twi.Status = 5 THEN 'Done' ELSE 'In Progress'
                        END AS Status,
                        CASE
                            WHEN twi.Status = 5 THEN 'Delivery'
                            WHEN tai.ActivityInstanceName LIKE '%C+A%' THEN 'Validation'
                            WHEN tai.ActivityInstanceName LIKE '%Export%' OR tai.ActivityInstanceName LIKE '%Exp%' THEN 'Delivery'
                            WHEN tai.ActivityInstanceName LIKE '%Import%' OR tai.ActivityInstanceName LIKE '%Imp%' THEN 'Import'
                            WHEN tai.ActivityInstanceName LIKE '%Extract%' OR tai.ActivityInstanceName LIKE '%OCR%' THEN 'Extraction'
                            WHEN tai.ActivityInstanceName LIKE '%Pause%' or tai.ActivityInstanceName like '%Deletion%' or tai.ActivityInstanceName like '%Lieferung%' THEN 'Delivery'
                            ELSE 'Extraction'
                        END AS CurrentStage,
                        wim.Priority,
                        (
                            SELECT t.TagID AS id, t.TagName AS name, t.TagColor AS color
                            FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                            JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                            WHERE wt.WorkItemID = twi.ID
                            FOR JSON PATH
                        ) AS TagsJSON,
                        ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                    FROM t_WorkItems twi
                    INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                    INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                    LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.WorkItemID
                    WHERE {full_where}
                )
                SELECT ModifiedAt, WorkItemID, Status, CurrentStage, Priority, TagsJSON
                FROM WorkitemCTE WHERE rn = 1
                ORDER BY ModifiedAt DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
                [*params, offset, limit],
            )
            rows = [
                {
                    "modifiedat": r.ModifiedAt,
                    "workitemid": r.WorkItemID,
                    "status": r.Status,
                    "current_stage": r.CurrentStage,
                    "priority": r.Priority or 0,
                    "tags": json.loads(r.TagsJSON) if r.TagsJSON else [],
                    "client": "default",
                }
                for r in cur.fetchall()
            ]
            return rows, total
        finally:
            conn.close()


def _qmarks(seq):
    return ", ".join(["?"] * len(seq))


def _chunked(seq, n=1000):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def resolve_nexora_filter_ids(filt):
    """Resolve tag/priority/assigned filters to a set of matching workitem ids
    from NexoraDB. Returns None when no NexoraDB-backed filter is active (i.e.
    no id constraint); returns a (possibly empty) set otherwise.

    Used by sources whose runtime DB cannot join NexoraDB in-query (Postgres).
    """
    active = []
    if filt.tag:
        active.append(("tag", filt.tag))
    if filt.priority:
        active.append(("priority", filt.priority))
    if filt.assigned_user:
        active.append(("assigned", filt.assigned_user))
    if not active:
        return None

    result = None
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        for kind, val in active:
            ids = set()
            if kind == "tag":
                cur.execute(
                    "SELECT DISTINCT wt.WorkItemID "
                    "FROM Workitem_Tags wt JOIN Tags t ON wt.TagID = t.TagID "
                    "WHERE t.TagName LIKE ?",
                    f"%{val}%",
                )
            elif kind == "priority":
                cur.execute(
                    "SELECT WorkItemID FROM Workitem_Metadata WHERE ISNULL(Priority, 0) = ?",
                    val,
                )
            else:  # assigned
                if val in ("None", "Unassigned"):
                    cur.execute(
                        "SELECT WorkItemID FROM Workitem_Metadata WHERE AssignedUserID IS NULL"
                    )
                else:
                    cur.execute(
                        "SELECT WorkItemID FROM Workitem_Metadata WHERE AssignedUserID = ?",
                        val,
                    )
            ids = {r.WorkItemID for r in cur.fetchall()}
            result = ids if result is None else (result & ids)
        return result if result is not None else set()
    except Exception as e:
        current_app.logger.error(f"resolve_nexora_filter_ids: {e}")
        return set()
    finally:
        conn.close()


def enrich_rows_from_nexora(rows):
    """Attach priority + tags to base rows from NexoraDB, keyed by workitemid.
    Mutates and returns ``rows``. Safe on an empty list."""
    ids = [r["workitemid"] for r in rows]
    if not ids:
        return rows
    by_id = {r["workitemid"]: r for r in rows}

    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        for chunk in _chunked(ids):
            ph = ", ".join(["?"] * len(chunk))
            cur.execute(
                f"SELECT WorkItemID, Priority FROM Workitem_Metadata WHERE WorkItemID IN ({ph})",
                list(chunk),
            )
            for r in cur.fetchall():
                if r.WorkItemID in by_id:
                    by_id[r.WorkItemID]["priority"] = r.Priority or 0
        for chunk in _chunked(ids):
            ph = ", ".join(["?"] * len(chunk))
            cur.execute(
                f"""
                SELECT wt.WorkItemID, t.TagID, t.TagName, t.TagColor
                FROM Workitem_Tags wt JOIN Tags t ON wt.TagID = t.TagID
                WHERE wt.WorkItemID IN ({ph})
                """,
                list(chunk),
            )
            for r in cur.fetchall():
                if r.WorkItemID in by_id:
                    by_id[r.WorkItemID]["tags"].append(
                        {"id": r.TagID, "name": r.TagName, "color": r.TagColor}
                    )
    except Exception as e:
        current_app.logger.error(f"enrich_rows_from_nexora: {e}")
    finally:
        conn.close()
    return rows
