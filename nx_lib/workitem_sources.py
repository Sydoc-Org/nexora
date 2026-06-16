"""Multi-source workitem runtime layer.

Each WorkitemSource wraps one runtime DB (SQL Server OctoDB or MS02 Postgres)
behind a uniform interface and emits the normalized row dict documented in the
plan. The merged-list endpoint fetches per source and merges in Python.

Module graph (no cycles): workitem_sources -> clients, db, config. It does NOT
import octo (document fetching stays in the views).
"""

import json
from dataclasses import dataclass, field

import psycopg2.extras
from flask import current_app

from . import config as cfg
from .clients import CLIENTS, non_default_clients
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

    def recent_rows(self, process_names, client_names, activity_ignore_csv, top=3):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT TOP {int(top)} twi.ID, twi.ModifiedAt, tp.Name AS ProcessName
                FROM t_WorkItems twi
                JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                JOIN t_Processes tp ON tp.ID = tai.ProcessID
                WHERE twi.Status <> 2
                  AND tp.Name IN ({_qmarks(process_names)})
                  AND tp.ClientName IN ({_qmarks(client_names)})
                  AND tai.ActivityInstanceName NOT IN ({activity_ignore_csv})
                ORDER BY twi.ModifiedAt DESC
                """,
                list(process_names) + list(client_names),
            )
            return [
                {
                    "id": r.ID,
                    "modifiedat": r.ModifiedAt,
                    "process": r.ProcessName,
                    "client": "default",
                }
                for r in cur.fetchall()
            ]
        except Exception as e:
            current_app.logger.error(f"SqlServerSource.recent_rows: {e}")
            return []
        finally:
            conn.close()

    def backlog_count(self, process_names, client_names):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT COUNT(*) FROM t_WorkItems w
                LEFT JOIN t_ActivityInstances a ON a.id = w.ActivityInstanceID
                LEFT JOIN t_Processes p ON p.id = a.ProcessID
                LEFT JOIN t_ActivityTypes act ON act.id = a.ActivityTypeID
                WHERE p.Name IN ({_qmarks(process_names)}) AND p.ClientName IN ({_qmarks(client_names)}) AND act.Name = 'C+A'
                """,
                list(process_names) + list(client_names),
            )
            return cur.fetchone()[0] or 0
        except Exception as e:
            current_app.logger.error(f"SqlServerSource.backlog_count: {e}")
            return 0
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


def _pgmarks(seq):
    return ", ".join(["%s"] * len(seq))


class PostgresSource:
    """MS02 client: Azure Postgres runtime DB. Same Octo schema, PG dialect.
    NexoraDB-backed filters are pre-resolved to an id allow-set; tags/priority
    are enriched app-side. Postgres identifiers are case-preserved PascalCase,
    so every table/column is double-quoted."""

    def __init__(self, CLIENTS_code="ms02"):  # noqa: N803
        self.code = CLIENTS_code
        client = CLIENTS.get(CLIENTS_code)
        self.engine = client.runtime_engine if client else None

    def has_workitem(self, workitem_id):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
            cur.execute('SELECT 1 FROM "t_WorkItems" WHERE "ID" = %s LIMIT 1', (workitem_id,))
            return cur.fetchone() is not None
        except Exception as e:
            current_app.logger.error(f"PostgresSource.has_workitem({workitem_id}): {e}")
            return False
        finally:
            conn.close()

    def _build_where(self, filt):
        clauses = [
            f'tp."Name" IN ({_pgmarks(filt.process_names)})',
            f'tp."ClientName" IN ({_pgmarks(filt.client_names)})',
            'twi."Status" <> 2',
        ]
        params = list(filt.process_names) + list(filt.client_names)
        # activity_ignore_csv is a literal "'A','B'" list (already escaped upstream).
        if filt.activity_ignore_csv:
            clauses.append(f'tai."ActivityInstanceName" NOT IN ({filt.activity_ignore_csv})')
        if filt.status_code is not None:
            clauses.append('twi."Status" = %s')
            params.append(filt.status_code)
        if filt.search_id:
            clauses.append('CAST(twi."ID" AS TEXT) LIKE %s')
            params.append(f"%{filt.search_id}%")
        if filt.start_date:
            clauses.append('twi."ModifiedAt" >= %s')
            params.append(filt.start_date)
        if filt.end_date:
            clauses.append('twi."ModifiedAt" < %s')
            params.append(filt.end_date)

        # NexoraDB-backed filters (tag/priority/assigned) -> id allow-set; those
        # metadata rows live in NexoraDB for workitems of every client.
        allow = resolve_nexora_filter_ids(filt)
        if allow is not None:
            if not allow:
                clauses.append("1=0")
            else:
                clauses.append('twi."ID" = ANY(%s)')
                params.append(list(allow))
        # Doc-field search -> in-query EXISTS against MS02's own t_DocumentIndexes
        # (Name/StringValue), one per (docfield, docvalue) pair, AND semantics.
        for name, value in zip(filt.docfields or [], filt.docvalues or [], strict=False):
            name = (name or "").strip()
            value = (value or "").strip()
            if not name or not value:
                continue
            clauses.append(
                'EXISTS (SELECT 1 FROM "t_DocumentIndexes" di '
                'WHERE di."WorkItemID" = twi."ID" AND di."Name" = %s AND di."StringValue" LIKE %s)'
            )
            params.append(name)
            params.append(f"%{value}%")
        return " AND ".join(clauses), params

    def list_workitems(self, filt, offset, limit):
        where, params = self._build_where(filt)
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
            cur.execute(
                f"""
                SELECT COUNT(twi."ID")
                FROM "t_WorkItems" twi
                JOIN "t_ActivityInstances" tai ON twi."ActivityInstanceID" = tai."ID"
                JOIN "t_Processes" tp ON tp."ID" = tai."ProcessID"
                WHERE {where}
                """,
                params,
            )
            total = cur.fetchone()[0] or 0

            cur.execute(
                f"""
                WITH ranked AS (
                    SELECT
                        twi."ModifiedAt" AS modifiedat,
                        twi."ID" AS workitemid,
                        CASE
                            WHEN twi."Status" = 0 THEN 'Ready'
                            WHEN twi."Status" = 5 THEN 'Done'
                            ELSE 'In Progress'
                        END AS status,
                        CASE
                            WHEN twi."Status" = 5 THEN 'Delivery'
                            WHEN tai."ActivityInstanceName" LIKE '%%C+A%%' THEN 'Validation'
                            WHEN tai."ActivityInstanceName" LIKE '%%Export%%' OR tai."ActivityInstanceName" LIKE '%%Exp%%' THEN 'Delivery'
                            WHEN tai."ActivityInstanceName" LIKE '%%Import%%' OR tai."ActivityInstanceName" LIKE '%%Imp%%' THEN 'Import'
                            WHEN tai."ActivityInstanceName" LIKE '%%Extract%%' OR tai."ActivityInstanceName" LIKE '%%OCR%%' THEN 'Extraction'
                            WHEN tai."ActivityInstanceName" LIKE '%%Pause%%' OR tai."ActivityInstanceName" LIKE '%%Deletion%%' OR tai."ActivityInstanceName" LIKE '%%Lieferung%%' THEN 'Delivery'
                            ELSE 'Extraction'
                        END AS currentstage,
                        ROW_NUMBER() OVER (PARTITION BY twi."ID" ORDER BY twi."ModifiedAt" DESC) AS rn
                    FROM "t_WorkItems" twi
                    JOIN "t_ActivityInstances" tai ON twi."ActivityInstanceID" = tai."ID"
                    JOIN "t_Processes" tp ON tp."ID" = tai."ProcessID"
                    WHERE {where}
                )
                SELECT modifiedat, workitemid, status, currentstage
                FROM ranked WHERE rn = 1
                ORDER BY modifiedat DESC
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            )
            rows = [
                {
                    "modifiedat": r.modifiedat,
                    "workitemid": r.workitemid,
                    "status": r.status,
                    "current_stage": r.currentstage,
                    "priority": 0,
                    "tags": [],
                    "client": self.code,
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

        enrich_rows_from_nexora(rows)
        return rows, total

    def recent_rows(self, process_names, client_names, activity_ignore_csv, top=3):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
            clauses = [
                'twi."Status" <> 2',
                f'tp."Name" IN ({_pgmarks(process_names)})',
                f'tp."ClientName" IN ({_pgmarks(client_names)})',
            ]
            params = list(process_names) + list(client_names)
            if activity_ignore_csv:
                clauses.append(f'tai."ActivityInstanceName" NOT IN ({activity_ignore_csv})')
            where = " AND ".join(clauses)
            cur.execute(
                f"""
                SELECT twi."ID" AS id, twi."ModifiedAt" AS modifiedat, tp."Name" AS process
                FROM "t_WorkItems" twi
                JOIN "t_ActivityInstances" tai ON twi."ActivityInstanceID" = tai."ID"
                JOIN "t_Processes" tp ON tp."ID" = tai."ProcessID"
                WHERE {where}
                ORDER BY twi."ModifiedAt" DESC
                LIMIT {int(top)}
                """,
                params,
            )
            return [
                {"id": r.id, "modifiedat": r.modifiedat, "process": r.process, "client": self.code}
                for r in cur.fetchall()
            ]
        except Exception as e:
            current_app.logger.error(f"PostgresSource.recent_rows: {e}")
            return []
        finally:
            conn.close()

    def backlog_count(self, process_names, client_names):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
            cur.execute(
                f"""
                SELECT COUNT(*) FROM "t_WorkItems" w
                LEFT JOIN "t_ActivityInstances" a ON a."ID" = w."ActivityInstanceID"
                LEFT JOIN "t_Processes" p ON p."ID" = a."ProcessID"
                LEFT JOIN "t_ActivityTypes" act ON act."ID" = a."ActivityTypeID"
                WHERE p."Name" IN ({_pgmarks(process_names)}) AND p."ClientName" IN ({_pgmarks(client_names)}) AND act."Name" = 'C+A'
                """,
                list(process_names) + list(client_names),
            )
            return cur.fetchone()[0] or 0
        except Exception as e:
            current_app.logger.error(f"PostgresSource.backlog_count: {e}")
            return 0
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


def active_sources():
    """All active sources, default first. Single-element list when MS02 absent."""
    sources = [SqlServerSource()]
    sources.extend(non_default_source_instances())
    return sources


def non_default_source_instances():
    """Source instances for every registered non-default client."""
    instances = []
    for client in non_default_clients():
        if client.dialect == "postgres":
            instances.append(PostgresSource(CLIENTS_code=client.code))
    return instances


def _cache_lookup(workitem_id):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ClientCode FROM WorkitemSourceCache WHERE WorkItemID = ?",
            str(workitem_id),
        )
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        current_app.logger.error(f"WorkitemSourceCache lookup({workitem_id}): {e}")
        return None
    finally:
        conn.close()


def _cache_store(workitem_id, client_code):
    """Idempotent upsert of id -> client_code. Only non-default ids are cached."""
    if client_code == "default":
        return
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE dbo.WorkitemSourceCache AS tgt
            USING (SELECT ? AS WorkItemID, ? AS ClientCode) AS src
            ON tgt.WorkItemID = src.WorkItemID
            WHEN MATCHED THEN UPDATE SET ClientCode = src.ClientCode, ResolvedAt = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT (WorkItemID, ClientCode) VALUES (src.WorkItemID, src.ClientCode);
            """,
            (str(workitem_id), client_code),
        )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"WorkitemSourceCache store({workitem_id}): {e}")
    finally:
        conn.close()


def get_source_for_workitem(workitem_id):
    """Resolve which client owns ``workitem_id``.

    Order of trust (collision fail-safe):
    1. Cache hit — authoritative.
    2. Probe ALL non-default sources. Exactly one claimant -> that client (cache
       it). Zero -> 'default'.
    3. FAIL-SAFE: more than one claimant means id spaces overlap — do NOT guess,
       log loudly and fall back to 'default'.
    """
    cached = _cache_lookup(workitem_id)
    if cached:
        return cached

    claimers = []
    for src in non_default_source_instances():
        try:
            if src.has_workitem(workitem_id):
                claimers.append(src.code)
        except Exception as e:
            current_app.logger.error(f"probe {src.code} for {workitem_id}: {e}")

    if len(claimers) == 1:
        _cache_store(workitem_id, claimers[0])
        return claimers[0]
    if len(claimers) > 1:
        current_app.logger.error(
            f"AMBIGUOUS workitem routing: id {workitem_id} claimed by {claimers}. "
            "ID spaces are no longer disjoint — falling back to 'default'. Switch "
            "to UI-carried client tags (compound identity) to disambiguate."
        )
    return "default"


def single_workitem_tags(workitem_id):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.TagID, t.TagName, t.TagColor
            FROM Workitem_Tags wt JOIN Tags t ON wt.TagID = t.TagID
            WHERE wt.WorkItemID = ?
            """,
            str(workitem_id),
        )
        return [{"id": r.TagID, "name": r.TagName, "color": r.TagColor} for r in cur.fetchall()]
    except Exception as e:
        current_app.logger.error(f"single_workitem_tags({workitem_id}): {e}")
        return []
    finally:
        conn.close()


def get_domain_for_workitem(workitem_id):
    """Octo domain for a workitem's owning client. Real replacement for the
    former octo.py stub."""
    code = get_source_for_workitem(workitem_id)
    client = CLIENTS.get(code) or CLIENTS["default"]
    return client.octo_domain


def fetch_merged_page(filt, offset, limit):
    """Fetch one page across all active sources.

    Returns ``(rows, total, degraded)`` where ``degraded`` is the list of client
    codes that errored (so the UI can show a non-blocking banner). A failed
    source contributes no rows and no count — the page still renders.

    Single active source: pass (offset, limit) straight through (byte-identical
    to the original single-DB behaviour). Multiple: fetch each source's top
    (offset+limit), merge by ModifiedAt desc, slice the page, sum counts.
    """
    sources = active_sources()
    if len(sources) == 1:
        try:
            rows, total = sources[0].list_workitems(filt, offset, limit)
            return rows, total, []
        except Exception as e:
            current_app.logger.error(f"source {sources[0].code} failed: {e}")
            return [], 0, [sources[0].code]

    per_source_rows = []
    total = 0
    degraded = []
    for src in sources:
        try:
            rows, count = src.list_workitems(filt, 0, offset + limit)
            per_source_rows.append(rows)
            total += count
        except Exception as e:
            current_app.logger.error(f"source {src.code} failed: {e}")
            degraded.append(src.code)
    merged = merge_sorted_rows(per_source_rows)
    page = merged[offset : offset + limit]

    # Warm the routing cache for non-default rows on this page.
    for r in page:
        if r["client"] != "default":
            _cache_store(r["workitemid"], r["client"])

    return page, total, degraded


def recent_activity_rows(process_names, client_names, activity_ignore_csv, top=3):
    """Top-N most recently modified workitems across all sources, merged.
    Each row: {id, modifiedat, process, client}."""
    out = []
    for src in active_sources():
        try:
            out.extend(src.recent_rows(process_names, client_names, activity_ignore_csv, top))
        except Exception as e:
            current_app.logger.error(f"recent_activity_rows {src.code}: {e}")
    out.sort(key=lambda r: r["modifiedat"], reverse=True)
    return out[:top]


def total_backlog_count(process_names, client_names):
    """Sum the C+A backlog count across all active sources (resilient)."""
    total = 0
    for src in active_sources():
        try:
            total += src.backlog_count(process_names, client_names)
        except Exception as e:
            current_app.logger.error(f"total_backlog_count {src.code}: {e}")
    return total
