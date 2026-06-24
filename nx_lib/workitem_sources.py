"""Multi-source workitem runtime layer.

Each WorkitemSource wraps one runtime DB (SQL Server OctoDB or MS02 Postgres)
behind a uniform interface and emits the normalized row dict documented in the
plan. The merged-list endpoint fetches per source and merges in Python.

Module graph (no cycles): workitem_sources -> clients, db, config. It does NOT
import octo (document fetching stays in the views).
"""

import contextlib
import io
import json
import re
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
    # Raw doc-field search pairs, kept for the autocomplete endpoint only. The
    # ACTUAL search is now ALWAYS pre-resolved by the orchestrator into a per-
    # source id allow-set:
    #   - SqlServerSource (default): SearchConfig -> StatisticsDB -> docfield_ids.
    #   - PostgresSource  (MS02):    SearchConfig -> engine_ms02_docfields_pg
    #                                (separate EAV doc-field DB) -> ms02_docfield_ids.
    # Neither source resolves the raw pairs in-query anymore.
    docfields: list = field(default_factory=list)
    docvalues: list = field(default_factory=list)
    # StatisticsDB-resolved id allow-set for the SQL SERVER source ONLY.
    docfield_ids: set | None = None
    # MS02 doc-field DB-resolved id allow-set for the Postgres source ONLY. Kept
    # separate from docfield_ids so a request that mixes default + MS02 processes
    # never lets one source's doc-field match shrink the other source's results.
    # None = no constraint; empty set = force zero rows; populated = ANY(%s).
    ms02_docfield_ids: set | None = None


def merge_sorted_rows(row_lists):
    """Merge per-source normalized rows into one list, newest first.

    Deterministic tie-break on workitemid (ascending) so equal timestamps order
    stably across sources. The tie-break key is stringified so equal-timestamp
    rows from different sources never raise TypeError when their id types differ
    (e.g. int vs str); ordering of same-timestamp rows is otherwise immaterial.
    """
    flat = [r for rows in row_lists for r in rows]
    flat.sort(key=lambda r: str(r["workitemid"]))
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


# OWNER-CONFIRMED doc-field index identifiers (see the plan's Owner-actions).
# These name the table + columns in the SEPARATE MS02 doc-field DB. Defaults
# mirror the runtime t_DocumentIndexes; if the owner confirms different names
# for THIS database, change them here (one place) -- both the resolver and the
# autocomplete branch read them.
# Plain SQL identifier (the field/id column names interpolated into MS02 queries
# come from admin-controlled SearchConfig, but we still validate before quoting).
_MS02_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ms02_id_column(join_condition, alias):
    """Pull the workitem-id column out of a SearchConfig JoinCondition like
    ``d.WorkItemID = twi.id`` -- the ``<alias>.<col>`` side. Returns the bare
    column name ('WorkItemID') or None. The same config row drives the default
    StatisticsDB path, which derives its id column from JoinCondition the same way."""
    if not join_condition or not alias:
        return None
    for part in re.split(r"\s*=\s*", join_condition.strip()):
        m = re.match(rf"^{re.escape(alias)}\.(\w+)$", part.strip(), re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _ms02_columnar_sql(table, id_col, field_col, time_filter, value_clause):
    """Build a columnar MS02 lookup against a per-client statistik table.

    The MS02 doc-field source is NOT an EAV table -- it is a wide table (e.g.
    ``public."DossierStatistik"``) with one column per field plus a workitem-id
    column. ``table`` (already schema-qualified/quoted) and ``time_filter`` come
    verbatim from SearchConfig (admin-controlled, like the default path); the
    id/field columns are validated as plain identifiers and double-quoted (PG is
    case-sensitive, so ``WorkItemID`` must be quoted). ``value_clause`` is the
    bound predicate applied to ``"<field>"::text`` -- ``ILIKE %s`` for search,
    ``= ANY(%s)`` for a PID list. Returns SQL, or None if an identifier is unsafe.
    """
    if not (table and id_col and field_col):
        return None
    if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(field_col)):
        current_app.logger.error(f"_ms02_columnar_sql: unsafe identifier {(id_col, field_col)}")
        return None
    sql = f'SELECT DISTINCT "{id_col}" FROM {table} WHERE "{field_col}"::text {value_clause}'
    if time_filter:
        sql += f" AND {time_filter}"
    return sql


def _as_workitem_ids(rows):
    """Coerce a statistik WorkItemID column (varchar in PG) to the int ids the
    runtime ``twi."ID"`` allow-set is matched against; non-numeric ids are dropped."""
    out = set()
    for row in rows:
        try:
            out.add(int(row[0]))
        except (TypeError, ValueError):
            continue
    return out


def resolve_ms02_docfield_ids(engine, pairs):
    """Resolve MS02 doc-field search to a workitem-id allow-set (columnar).

    ``pairs`` is ``[(specs, value), ...]`` -- one entry per searched docfield,
    where ``specs`` is the list of ``(table, id_col, field_col, time_filter)``
    config rows the docfield maps to (from the 'ms02' SearchConfig rows; usually
    one). Within a docfield the rows are OR'd; docfields are AND-intersected. The
    field-column match is case-insensitive (ILIKE), matching the default SQL
    Server path's collation.

    Three-way contract (mirrors the DEFAULT docfield pre-fetch block):
      * None      -> no constraint (engine absent, no pairs, or any error).
      * set()     -> a docfield matched nothing -> force zero MS02 rows.
      * {ids...}  -> intersected allow-set -> twi."ID" = ANY(%s).
    Never raises: on error it logs and returns None (no constraint).
    """
    if engine is None or not pairs:
        return None

    result = None
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        for specs, value in pairs:
            field_ids = set()
            for table, id_col, field_col, time_filter in specs:
                sql = _ms02_columnar_sql(table, id_col, field_col, time_filter, "ILIKE %s")
                if sql is None:
                    continue
                cur.execute(sql, [f"%{value}%"])
                field_ids |= _as_workitem_ids(cur.fetchall())
            if not field_ids:
                return set()  # a docfield matched nothing -> whole result empty
            result = field_ids if result is None else (result & field_ids)
        return result
    except Exception as e:
        current_app.logger.error(f"resolve_ms02_docfield_ids: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


_PREPARED_TRUE = {"true", "1", "yes", "y", "ja", "x", "wahr"}
_PREPARED_MAX_ROWS = 10000  # bound a malicious/oversized workbook


def _norm_pid(value):
    """Stringify a cell value as a PID without Excel's float trailing '.0'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_prepared_xlsx(data):
    """Parse the MS02 'prepared documents' xlsx into a list of row dicts.

    Columns (case-insensitive, order-agnostic): PID, Collected (bool),
    CollectedBy (name), Prepared (bool), PreparedBy (name). The real-world
    header has a DUPLICATE 'PreparedBy' — the 4th column is the Prepared flag
    (user typo). The parser resolves duplicates by positional first-wins:
    first 'PreparedBy' fills the Prepared flag slot; second fills PreparedBy.

    Backward-compatible: a 2-column file (PID + Prepared) returns dicts with
    collected=False, collected_by='', prepared_by=''.

    Slot assignment: each normalized header key maps to an ordered list of
    slots it can fill (first unfilled slot wins):
      'pid'         -> [pid]
      'collected'   -> [collected_flag]
      'collectedby' -> [collected_by]
      'prepared'    -> [prepared_flag]
      'preparedby'  -> [prepared_flag, prepared_by]   # handles the typo

    Returns (rows, error):
      rows: list[dict] with keys pid/collected/collected_by/prepared/prepared_by;
            deduped on pid (first wins); blanks/blank-pid rows skipped;
            at most _PREPARED_MAX_ROWS rows.
      error: None on success or a short human message on failure. NEVER raises.
    """
    import openpyxl  # local import: openpyxl is heavyish and only used here

    key_to_slots = {
        "pid": ["pid"],
        "collected": ["collected_flag"],
        "collectedby": ["collected_by"],
        "prepared": ["prepared_flag"],
        "preparedby": ["prepared_flag", "prepared_by"],
    }

    def _norm_header(cell):
        return (
            str(cell).strip().lower().replace(" ", "").replace("_", "") if cell is not None else ""
        )

    def _to_bool(raw):
        if isinstance(raw, bool):
            return raw
        if raw is None:
            return False
        return str(raw).strip().lower() in _PREPARED_TRUE

    def _to_str(raw):
        if raw is None:
            return ""
        if isinstance(raw, float) and raw.is_integer():
            return str(int(raw))
        return str(raw).strip()

    def _log(msg):
        with contextlib.suppress(RuntimeError):  # no app context in unit tests
            current_app.logger.error(msg)

    wb = None
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        _log(f"parse_prepared_xlsx load: {e}")
        return [], "Could not read the Excel file."
    try:
        sh = wb.active
        rows_iter = sh.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            return [], "The Excel file is empty."

        # Build slot -> column_index map (first-wins per slot).
        assigned = {}  # slot -> column index
        for i, cell in enumerate(header or []):
            key = _norm_header(cell)
            for slot in key_to_slots.get(key, []):
                if slot not in assigned:
                    assigned[slot] = i
                    break

        if "pid" not in assigned:
            return [], "Missing required 'PID' column."

        pid_i = assigned["pid"]
        col_i = assigned.get("collected_flag")
        cby_i = assigned.get("collected_by")
        prep_i = assigned.get("prepared_flag")
        pby_i = assigned.get("prepared_by")

        out = []
        seen = set()
        for row in rows_iter:
            if len(out) >= _PREPARED_MAX_ROWS:
                break
            if row is None:
                continue
            pid = _norm_pid(row[pid_i] if pid_i < len(row) else None)
            if not pid or pid in seen:
                continue
            seen.add(pid)

            def _cell(idx, row=row):
                return row[idx] if idx is not None and idx < len(row) else None

            out.append(
                {
                    "pid": pid,
                    "collected": _to_bool(_cell(col_i)),
                    "collected_by": _to_str(_cell(cby_i)),
                    "prepared": _to_bool(_cell(prep_i)),
                    "prepared_by": _to_str(_cell(pby_i)),
                }
            )
        return out, None
    except Exception as e:
        _log(f"parse_prepared_xlsx: {e}")
        return [], "Could not parse the Excel file."
    finally:
        if wb is not None:
            with contextlib.suppress(Exception):
                wb.close()


def resolve_ms02_pid_ids(engine, specs, pid_values):
    """Resolve a list of personal-number PIDs to an MS02 workitem-id allow-set
    (columnar).

    ``specs`` is the list of ``(table, id_col, pid_col, time_filter)`` config rows
    the PID column maps to (from the 'ms02' SearchConfig col_pid rows -- never
    hard-coded; usually one). ``pid_values`` is the deduped PID list from the
    uploaded Excel. Matching is EXACT (``= ANY``), not ILIKE, since PIDs are
    precise identifiers. One PID can map to many workitems; the result is the
    UNION across all specs.

    Three-way contract (mirrors resolve_ms02_docfield_ids):
      * None      -> no constraint (engine absent, no specs, no PIDs, or error).
      * set()     -> no PID matched a workitem -> force zero MS02 rows.
      * {ids...}  -> union allow-set -> twi."ID" = ANY(%s).
    Never raises: on error it logs and returns None (no constraint).
    """
    if engine is None or not specs or not pid_values:
        return None
    pid_list = [str(p) for p in pid_values]
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        ids = set()
        for table, id_col, pid_col, time_filter in specs:
            sql = _ms02_columnar_sql(table, id_col, pid_col, time_filter, "= ANY(%s)")
            if sql is None:
                continue
            cur.execute(sql, [pid_list])
            ids |= _as_workitem_ids(cur.fetchall())
        return ids
    except Exception as e:
        current_app.logger.error(f"resolve_ms02_pid_ids: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def resolve_ms02_pid_to_wids(engine, specs, pid_values):
    """Resolve a list of personal-number PIDs to a per-PID workitem-id map
    (columnar). Sibling of resolve_ms02_pid_ids; returns the per-PID mapping
    needed to merge import values onto matched rows and detect unmatched PIDs
    (for synthetic-row generation).

    Reuses _ms02_columnar_sql / _MS02_IDENT / _as_workitem_ids to avoid
    duplicating identifier-safety logic. Projects both the pid and id columns
    by wrapping the columnar SQL: SELECT DISTINCT "pid_col"::text, "id_col".

    Three-way contract (mirrors resolve_ms02_pid_ids):
      * None        -> no constraint (engine absent, no specs, no PIDs, error).
      * {}          -> no PID matched any workitem (zero rows from DB).
      * {pid: [...]}-> matched PIDs only; unmatched PIDs are ABSENT from dict.
    Never raises: on error it logs and returns None.
    """
    if engine is None or not specs or not pid_values:
        return None
    pid_list = [str(p) for p in pid_values]
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        result: dict[str, list[int]] = {}
        for table, id_col, pid_col, time_filter in specs:
            # Validate identifiers using the same _MS02_IDENT guard as
            # _ms02_columnar_sql — keeps security logic in one place.
            if not (table and id_col and pid_col):
                continue
            if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(pid_col)):
                current_app.logger.error(
                    f"resolve_ms02_pid_to_wids: unsafe identifier {(id_col, pid_col)}"
                )
                continue
            sql = (
                f'SELECT DISTINCT "{pid_col}"::text, "{id_col}"'
                f" FROM {table}"
                f' WHERE "{pid_col}"::text = ANY(%s)'
            )
            if time_filter:
                sql += f" AND {time_filter}"
            cur.execute(sql, [pid_list])
            for pid_raw, wid_raw in cur.fetchall():
                pid_str = str(pid_raw) if pid_raw is not None else None
                if not pid_str:
                    continue
                wids = _as_workitem_ids([(wid_raw,)])
                if not wids:
                    continue
                wid = next(iter(wids))
                if pid_str not in result:
                    result[pid_str] = []
                if wid not in result[pid_str]:
                    result[pid_str].append(wid)
        return result
    except Exception as e:
        current_app.logger.error(f"resolve_ms02_pid_to_wids: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def resolve_ms02_wids_to_pids(engine, specs, wids):
    """Inverse of resolve_ms02_pid_to_wids: map workitem ids -> their PID (col_pid)
    value, columnar. Used by the reverse 'In register' chip to learn each visible
    workitem's PID. Reuses the _MS02_IDENT guard + _as_workitem_ids.

    None (engine/specs/wids absent or error) -> no mapping; {} -> none matched;
    {wid: pid} otherwise. First PID seen per wid wins. Never raises."""
    if engine is None or not specs or not wids:
        return None
    ids = []
    for w in wids:
        try:
            ids.append(int(w))
        except (TypeError, ValueError):
            continue
    if not ids:
        return None
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        result: dict[int, str] = {}
        for table, id_col, pid_col, time_filter in specs:
            if not (table and id_col and pid_col):
                continue
            if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(pid_col)):
                current_app.logger.error(
                    f"resolve_ms02_wids_to_pids: unsafe identifier {(id_col, pid_col)}"
                )
                continue
            sql = (
                f'SELECT DISTINCT "{id_col}", "{pid_col}"::text'
                f" FROM {table}"
                f' WHERE "{id_col}" = ANY(%s)'
            )
            if time_filter:
                sql += f" AND {time_filter}"
            cur.execute(sql, [ids])
            for wid_raw, pid_raw in cur.fetchall():
                wids_parsed = _as_workitem_ids([(wid_raw,)])
                if not wids_parsed:
                    continue
                wid = next(iter(wids_parsed))
                pid_str = str(pid_raw) if pid_raw is not None else None
                if pid_str and wid not in result:
                    result[wid] = pid_str
        return result
    except Exception as e:
        current_app.logger.error(f"resolve_ms02_wids_to_pids: {e}")
        return None
    finally:
        if conn is not None:
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
        # Doc-field search -> pre-resolved id allow-set against the SEPARATE MS02
        # doc-field DB (engine_ms02_docfields_pg). The orchestrator resolves the
        # SearchConfig-mapped EAV match into filt.ms02_docfield_ids BEFORE this
        # runs, because a single PG connection binds to one database and cannot
        # join the doc-field DB to the runtime DB in-query. Same three-way
        # contract as the NexoraDB allow-set above.
        if filt.ms02_docfield_ids is not None:
            if not filt.ms02_docfield_ids:
                clauses.append("1=0")
            else:
                clauses.append('twi."ID" = ANY(%s)')
                params.append(list(filt.ms02_docfield_ids))
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

    # The page total is the sum of per-source counts. This is exact because
    # workitem ids are globally unique across sources (the disjoint-id invariant
    # the routing fail-safe in get_source_for_workitem enforces): no workitem is
    # counted by more than one source. If id spaces ever overlap, this total
    # could double-count — that's the trigger to move to compound identity.
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
