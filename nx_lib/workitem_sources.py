"""Multi-source workitem runtime layer.

Each WorkitemSource wraps one runtime DB (SQL Server OctoDB or MS02 Postgres)
behind a uniform interface and emits the normalized row dict documented in the
plan. The merged-list endpoint fetches per source and merges in Python.

Module graph (no cycles): workitem_sources -> clients, db, config. It does NOT
import octo (document fetching stays in the views).
"""

import contextlib
import io
import re
from dataclasses import dataclass, field

import psycopg2.extras
from flask import current_app

from .clients import CLIENTS, non_default_clients
from .db import engine_nexora_db

# Status code the UI's "In Progress" option maps to. It is a BUCKET, not a
# single code: the display CASE renders every status that is not 0 (Ready) or
# 5 (Done) as "In Progress", so both sources filter it as `NOT IN (0, 5)`.
_STATUS_IN_PROGRESS = 1

# Soft-deleted workitems. Hidden from every list unless the caller explicitly
# filtered FOR them, which the view only allows for holders of
# workitems.filter.status.deleted (internal-only permission, issue #125).
_STATUS_DELETED = 2


@dataclass
class WorkitemFilter:
    """Dialect-neutral bag of the list filters. Each source renders its own SQL."""

    # [(client, process), ...] allow-list (from permissions), rendered as an
    # OR-joined (client = ? AND process = ?) pair predicate by each source.
    # NEVER split into independent client/process IN-lists -- ANDing two
    # independent IN-lists authorizes their full cross product (a caller
    # granted only (A, P1) and (B, P2) would also read (A, P2) and (B, P1)).
    client_process_pairs: list
    activity_ignore_csv: str  # "'A','B'" string from ActivityInstancesToIgnore
    status_code: int | None = None
    search_id: str | None = None  # workitem id prefix to match (e.g. "11" -> 11, 110, 1199, ...)
    start_date: object = None
    end_date: object = None
    # One of 'Import' | 'Extraction' | 'Validation' | 'Delivery' -- matched
    # against the SAME derived-stage CASE the list query already computes
    # (each source's CurrentStage/currentstage column), on the workitem's
    # latest activity row only (rn = 1). Filtering pre-dedup would be wrong:
    # a workitem can have earlier activity rows in other stages.
    stage: str | None = None
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


def merge_sorted_rows(row_lists, search_id=None):
    """Merge per-source normalized rows into one list, newest first.

    Deterministic tie-break on workitemid (ascending) so equal timestamps order
    stably across sources. The tie-break key is stringified so equal-timestamp
    rows from different sources never raise TypeError when their id types differ
    (e.g. int vs str); ordering of same-timestamp rows is otherwise immaterial.

    search_id: when a workitem-id prefix search is active, relevance (shortest
    id first -- the same reasoning as each source's own ORDER BY, see
    list_workitems) takes priority over recency, since sort() is stable and
    this key is applied *last*. Each per-source list already arrives in this
    relevance order from its own query; this re-establishes it across sources
    after the merge, since plain recency would otherwise scramble it back.
    """
    flat = [r for rows in row_lists for r in rows]
    flat.sort(key=lambda r: str(r["workitemid"]))
    flat.sort(key=lambda r: r["modifiedat"], reverse=True)
    if search_id:
        flat.sort(key=lambda r: len(str(r["workitemid"])))
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

    def process_of(self, workitem_id):
        """(ClientName, ProcessName) for a workitem, or None if not found /
        on error. Same namespace the list query authorizes against
        (tp.ClientName / tp.Name) — the detail-access entitlement check (#193)
        compares this pair to the caller's granted process pairs."""
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT TOP 1 tp.ClientName, tp.Name "
                "FROM t_WorkItems twi "
                "JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID "
                "JOIN t_Processes tp ON tp.ID = tai.ProcessID "
                "WHERE twi.ID = ?",
                workitem_id,
            )
            row = cur.fetchone()
            return (row[0], row[1]) if row else None
        except Exception as e:
            current_app.logger.error(f"SqlServerSource.process_of({workitem_id}): {e}")
            return None
        finally:
            conn.close()

    def list_workitems(self, filt, offset, limit):
        """Return (rows, total_count). Builds the same WHERE + SQL the original
        _get_workitems_data ran against engine_octo_db."""
        # Zero permitted pairs -> `1=0`, an always-false predicate that keeps
        # the query syntactically valid (an empty `IN ()` was a syntax error
        # that surfaced as a degraded-source banner instead of a clean empty
        # list).
        if not filt.client_process_pairs:
            return [], 0
        pair_sql, pair_params = _pair_predicate(
            filt.client_process_pairs, "tp.ClientName", "tp.Name", "?"
        )
        where_clauses = [f"({pair_sql})"]
        if filt.status_code != _STATUS_DELETED:
            where_clauses.append("twi.Status <> 2")
        if filt.activity_ignore_csv:
            where_clauses.append(f"tai.ActivityInstanceName not in ({filt.activity_ignore_csv})")
        params = list(pair_params)

        if filt.status_code is not None:
            # The display CASE maps 0 -> Ready, 5 -> Done and EVERYTHING ELSE to
            # 'In Progress' (live data really carries 3 and 4), so filtering the
            # In-Progress bucket must match the same set -- `Status = 1` hid 96
            # rows that the list showed as In Progress.
            if filt.status_code == _STATUS_IN_PROGRESS:
                where_clauses.append("twi.Status NOT IN (0, 5)")
            else:
                where_clauses.append("twi.Status = ?")
                params.append(filt.status_code)
        if filt.search_id:
            # Prefix match: searching 11 returns 11/110/1199/... but not
            # 911/3211 -- LIKE 'id%', not '%id%' (a full substring match
            # would also pull in 1371/3716/16371 for a search of 371, which
            # is the one thing this deliberately still avoids). The '%' is
            # appended to the bound value, not the SQL text, so it's still a
            # literal for LIKE's purposes on this call, not something the
            # caller could inject wildcards through beyond their own prefix.
            where_clauses.append("CAST(twi.id AS NVARCHAR(50)) LIKE ?")
            params.append(str(filt.search_id).strip() + "%")
        if filt.start_date:
            where_clauses.append("twi.ModifiedAt >= ?")
            params.append(filt.start_date)
        if filt.end_date:
            where_clauses.append("twi.ModifiedAt < ?")
            params.append(filt.end_date)

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

            cte_sql = f"""
                WITH WorkitemCTE AS (
                    SELECT
                        twi.ModifiedAt, twi.ID AS WorkItemID,
                        CASE
                            WHEN twi.Status = 0 THEN 'Ready' WHEN twi.Status = 5 THEN 'Done'
                            WHEN twi.Status = 2 THEN 'Deleted' ELSE 'In Progress'
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
                        ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                    FROM t_WorkItems twi
                    INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                    INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                    WHERE {full_where}
                ),
                LatestCTE AS (
                    SELECT * FROM WorkitemCTE WHERE rn = 1
                )
            """
            # Stage is filtered post-dedup (on the workitem's latest activity
            # row only), so it's applied against LatestCTE, not full_where.
            stage_clause = "WHERE CurrentStage = ?" if filt.stage else ""
            stage_params = [filt.stage] if filt.stage else []

            # A workitem-id prefix search ranks by relevance first: the
            # fewer extra digits an id has beyond the searched prefix, the
            # closer/more-matching it is (an exact-length match is the best
            # possible match). Shortest id wins; ModifiedAt DESC only breaks
            # ties among same-length ids. No search -> unchanged recency sort.
            order_clause = (
                "ORDER BY LEN(CAST(WorkItemID AS NVARCHAR(50))) ASC, ModifiedAt DESC"
                if filt.search_id
                else "ORDER BY ModifiedAt DESC"
            )

            cur.execute(
                cte_sql + f"SELECT COUNT(*) FROM LatestCTE {stage_clause}",
                [*params, *stage_params],
            )
            total = cur.fetchone()[0] or 0

            cur.execute(
                cte_sql
                + f"""
                SELECT ModifiedAt, WorkItemID, Status, CurrentStage
                FROM LatestCTE {stage_clause}
                {order_clause}
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
                [*params, *stage_params, offset, limit],
            )
            rows = [
                {
                    "modifiedat": r.ModifiedAt,
                    "workitemid": r.WorkItemID,
                    "status": r.Status,
                    "current_stage": r.CurrentStage,
                    "client": "default",
                }
                for r in cur.fetchall()
            ]
            return rows, total
        finally:
            conn.close()

    def recent_rows(self, pairs, activity_ignore_csv, top=3):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor()
            pair_sql, pair_params = _pair_predicate(pairs, "tp.ClientName", "tp.Name", "?")
            where_clauses = [
                "twi.Status <> 2",
                f"({pair_sql})",
            ]
            if activity_ignore_csv:
                where_clauses.append(f"tai.ActivityInstanceName NOT IN ({activity_ignore_csv})")
            where = " AND ".join(where_clauses)
            cur.execute(
                f"""
                SELECT TOP {int(top)} twi.ID, twi.ModifiedAt, tp.Name AS ProcessName
                FROM t_WorkItems twi
                JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                JOIN t_Processes tp ON tp.ID = tai.ProcessID
                WHERE {where}
                ORDER BY twi.ModifiedAt DESC
                """,
                pair_params,
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

    def backlog_count(self, pairs):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor()
            pair_sql, pair_params = _pair_predicate(pairs, "p.ClientName", "p.Name", "?")
            cur.execute(
                f"""
                SELECT COUNT(*) FROM t_WorkItems w
                LEFT JOIN t_ActivityInstances a ON a.id = w.ActivityInstanceID
                LEFT JOIN t_Processes p ON p.id = a.ProcessID
                LEFT JOIN t_ActivityTypes act ON act.id = a.ActivityTypeID
                WHERE ({pair_sql}) AND act.Name = 'C+A'
                """,
                pair_params,
            )
            return cur.fetchone()[0] or 0
        except Exception as e:
            current_app.logger.error(f"SqlServerSource.backlog_count: {e}")
            return 0
        finally:
            conn.close()


def _qmarks(seq):
    return ", ".join(["?"] * len(seq))


def _pair_predicate(pairs, client_expr, process_expr, marker):
    """Build an OR-joined parameterized (client, process) pair predicate --
    e.g. "(tp.ClientName = ? AND tp.Name = ?) OR (...)" -- from a list of
    (client, process) tuples, instead of two independent client/process
    IN-lists (ANDed together, those authorize the full cross product: a
    caller granted only (A, P1) and (B, P2) would also match (A, P2) and
    (B, P1)). Returns (sql, params); sql is the always-false "1=0" for an
    empty pairs list so callers get a syntactically valid clause instead of
    an `IN ()` error."""
    if not pairs:
        return "1=0", []
    sql = " OR ".join(f"({client_expr} = {marker} AND {process_expr} = {marker})" for _ in pairs)
    params = [value for pair in pairs for value in pair]
    return sql, params


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


# Int-type bucket for the MS02 (Postgres) typed-predicate fast path (#98 Task
# 12). Values MUST match FieldMapping.ColumnType / ProcessSource.IdColumnType
# exactly as seeded by scripts/seed_column_types.py (migration 0076) --
# lowercase information_schema.columns values on the PG side (e.g.
# 'character varying', 'bigint'). A mismatch here silently disables the fast
# path (falls through to the always-correct ``::text`` fallback below), it
# never misfires the bare-column path against a non-numeric value.
_MS02_INT_TYPES = {"int", "bigint", "smallint", "tinyint", "integer"}

# value_clause shapes that compare a column to a fully-typed bind value (as
# opposed to ILIKE, which always needs the text cast) -- these are the only
# shapes eligible for the typed/bare-column fast path.
_MS02_EXACT_MATCH_CLAUSES = {"= %s", "= ANY(%s)"}


def _ms02_columnar_sql(table, id_col, field_col, time_filter, value_clause, field_type=None):
    """Build a columnar MS02 lookup against a per-client statistik table.

    The MS02 doc-field source is NOT an EAV table -- it is a wide table (e.g.
    ``public."DossierStatistik"``) with one column per field plus a workitem-id
    column. ``table`` (already schema-qualified/quoted) and ``time_filter`` come
    verbatim from SearchConfig (admin-controlled, like the default path); the
    id/field columns are validated as plain identifiers and double-quoted (PG is
    case-sensitive, so ``WorkItemID`` must be quoted). ``value_clause`` is the
    bound predicate applied to ``field_col`` -- ``ILIKE %s`` for search,
    ``= ANY(%s)`` for a list. Returns SQL, or None if an identifier is unsafe.

    ``field_type`` (#98 Task 12): when it is int-typed (``_MS02_INT_TYPES``)
    AND ``value_clause`` is an exact-match shape (``_MS02_EXACT_MATCH_CLAUSES``
    -- ``= %s`` / ``= ANY(%s)``), the predicate compares the bare column
    (sargable, no cast) -- the CALLER is responsible for binding already-typed
    int params in that case. Every other combination keeps the legacy
    ``"<field>"::text`` cast, which is always correct.
    """
    if not (table and id_col and field_col):
        return None
    if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(field_col)):
        current_app.logger.error(f"_ms02_columnar_sql: unsafe identifier {(id_col, field_col)}")
        return None
    if field_type in _MS02_INT_TYPES and value_clause in _MS02_EXACT_MATCH_CLAUSES:
        sql = f'SELECT DISTINCT "{id_col}" FROM {table} WHERE "{field_col}" {value_clause}'
    else:
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


def _pg_like_escape(value):
    """Escape LIKE metacharacters so an ILIKE comparison is a literal match."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Whitelisted doc-value operators on the MS02 (Postgres) leg (issue #148):
# op key -> (comparator template, param builder). Everything runs through
# ILIKE so case-insensitivity matches the default SQL Server path's CI
# collation; eq/neq escape the value so they compare literally. The LIKE
# family keeps the historical no-wildcard-escaping behavior.
_MS02_DOCFIELD_OPS = {
    "contains": ("ILIKE %s", lambda v: f"%{v}%"),
    "ncontains": ("NOT ILIKE %s", lambda v: f"%{v}%"),
    "eq": ("ILIKE %s", _pg_like_escape),
    "neq": ("NOT ILIKE %s", _pg_like_escape),
    "startswith": ("ILIKE %s", lambda v: f"{v}%"),
    "endswith": ("ILIKE %s", lambda v: f"%{v}"),
}


def resolve_ms02_docfield_ids(engine, pairs):
    """Resolve MS02 doc-field search to a workitem-id allow-set (columnar).

    ``pairs`` is ``[(specs, value[, op[, comb]]), ...]`` -- one entry per
    searched docfield, where ``specs`` is the list of
    ``(table, id_col, field_col, time_filter[, field_type])`` config rows the
    docfield maps to (from the 'ms02' SearchConfig rows; usually one) -- the
    5th ``field_type`` element (#98 Task 12) is optional, a bare 4-tuple is
    still accepted (``field_type=None``, always the ``::text`` fallback). An
    EMPTY specs list is a forced-empty pair (field unmapped -> contributes
    set()). Within a pair the spec rows are OR'd; pairs fold left-to-right
    joined by their ``comb`` ('and' intersects, 'or' unions; the first pair's
    comb is ignored). ``op`` is a _MS02_DOCFIELD_OPS key ('contains'
    fallback). Matching is case-insensitive (ILIKE), matching the default SQL
    Server path's collation -- EXCEPT the int-typed ``eq`` fast path below,
    which is an exact numeric compare (case-insensitivity is meaningless for
    an int column).

    Typed fast path (#98 Task 12): when a spec's ``field_type`` is int-typed
    (``_MS02_INT_TYPES``) and ``op == "eq"``, the value is parsed as int and
    compared with a bare, sargable ``"<field>" = %s`` instead of
    ``"<field>"::text ILIKE %s``. A non-numeric value can never equal an int
    column, so an unparseable value makes that ONE spec contribute nothing
    (skipped, not an error) -- other specs in the same pair (OR'd) are
    unaffected. Every other op/type combination is unchanged (``::text``
    fallback).

    Three-way contract (mirrors the DEFAULT docfield pre-fetch block):
      * None      -> unresolved (engine absent, no pairs, or any error). The
                     view coerces this to set() for an active doc-field search
                     (fail closed) -- None never reaches the source as
                     "no constraint" while a doc-field filter is in play.
      * set()     -> the folded pairs matched nothing -> force zero MS02 rows.
      * {ids...}  -> folded allow-set -> twi."ID" = ANY(%s).
    Never raises: on error it logs and returns None (no constraint).
    """
    if engine is None or not pairs:
        return None

    result = None
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        for entry in pairs:
            specs, value = entry[0], entry[1]
            op = entry[2] if len(entry) > 2 else "contains"
            comb = entry[3] if len(entry) > 3 else "and"
            comparator, param_of = _MS02_DOCFIELD_OPS.get(op, _MS02_DOCFIELD_OPS["contains"])
            field_ids = set()
            for spec in specs:
                table, id_col, field_col, time_filter = spec[0], spec[1], spec[2], spec[3]
                field_type = spec[4] if len(spec) > 4 else None
                if field_type in _MS02_INT_TYPES and op == "eq":
                    try:
                        int_value = int(value)
                    except (TypeError, ValueError):
                        continue  # unparseable -> this spec can't match an int column
                    sql = _ms02_columnar_sql(
                        table, id_col, field_col, time_filter, "= %s", field_type
                    )
                    if sql is None:
                        continue
                    cur.execute(sql, [int_value])
                else:
                    sql = _ms02_columnar_sql(table, id_col, field_col, time_filter, comparator)
                    if sql is None:
                        continue
                    cur.execute(sql, [param_of(value)])
                field_ids |= _as_workitem_ids(cur.fetchall())
            if result is None:
                result = field_ids
            elif comb == "or":
                result = result | field_ids
            else:
                result = result & field_ids
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

    ``specs`` is the list of ``(table, id_col, pid_col, time_filter[,
    pid_column_type])`` config rows the PID column maps to (from the 'ms02'
    SearchConfig col_pid rows -- never hard-coded; usually one; a bare 4-tuple
    is still accepted, ``pid_column_type=None``). ``pid_values`` is the
    deduped PID list from the uploaded Excel. Matching is EXACT (``= ANY``),
    not ILIKE, since PIDs are precise identifiers. One PID can map to many
    workitems; the result is the UNION across all specs.

    Typed fast path (#98 Task 12): when a spec's ``pid_column_type`` is
    int-typed (``_MS02_INT_TYPES``), the PID list is parsed to ints and
    compared with a bare, sargable ``"<pid_col>" = ANY(%s)``. If ANY PID in
    the list fails to parse, that spec is skipped entirely (contributes
    nothing) -- other specs are unaffected.

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
        for spec in specs:
            table, id_col, pid_col, time_filter = spec[0], spec[1], spec[2], spec[3]
            field_type = spec[4] if len(spec) > 4 else None
            if field_type in _MS02_INT_TYPES:
                # An unparseable PID can't match an int column -- drop just
                # that value (I2), not the whole spec's batch of valid PIDs.
                values = []
                for p in pid_list:
                    try:
                        values.append(int(p))
                    except (TypeError, ValueError):
                        continue
                if not values:
                    continue  # every PID in the batch was unparseable
                value_clause = "= ANY(%s)"
            else:
                values = pid_list
                value_clause = "= ANY(%s)"
            sql = _ms02_columnar_sql(table, id_col, pid_col, time_filter, value_clause, field_type)
            if sql is None:
                continue
            cur.execute(sql, [values])
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

    Reuses _MS02_IDENT / _as_workitem_ids to avoid duplicating identifier-
    safety logic. Projects both the pid and id columns: SELECT DISTINCT
    "pid_col", "id_col" -- the pid projection is cast to text UNLESS the
    spec's ``pid_column_type`` (5th tuple element, #98 Task 12) is int-typed
    (``_MS02_INT_TYPES``), in which case both the projection and the ``= ANY``
    comparison stay bare/native-int (sargable), and the bound PID list is
    parsed to ints -- an unparseable PID skips that one spec, same as
    resolve_ms02_pid_ids. A bare 4-tuple spec is still accepted
    (``pid_column_type=None``, always the ``::text`` fallback).

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
        for spec in specs:
            table, id_col, pid_col, time_filter = spec[0], spec[1], spec[2], spec[3]
            field_type = spec[4] if len(spec) > 4 else None
            # Validate identifiers using the same _MS02_IDENT guard as
            # _ms02_columnar_sql — keeps security logic in one place.
            if not (table and id_col and pid_col):
                continue
            if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(pid_col)):
                current_app.logger.error(
                    f"resolve_ms02_pid_to_wids: unsafe identifier {(id_col, pid_col)}"
                )
                continue
            if field_type in _MS02_INT_TYPES:
                # An unparseable PID can't match an int column -- drop just
                # that value (I2), not the whole spec's batch of valid PIDs.
                values = []
                for p in pid_list:
                    try:
                        values.append(int(p))
                    except (TypeError, ValueError):
                        continue
                if not values:
                    continue  # every PID in the batch was unparseable
                sql = (
                    f'SELECT DISTINCT "{pid_col}", "{id_col}"'
                    f" FROM {table}"
                    f' WHERE "{pid_col}" = ANY(%s)'
                )
            else:
                values = pid_list
                sql = (
                    f'SELECT DISTINCT "{pid_col}"::text, "{id_col}"'
                    f" FROM {table}"
                    f' WHERE "{pid_col}"::text = ANY(%s)'
                )
            if time_filter:
                sql += f" AND {time_filter}"
            cur.execute(sql, [values])
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


def resolve_octo_wid_stage(engine, wid):
    """Latest (status, current_stage) for a single default-client Octo
    workitem, using the same CASE-over-join vocabulary the list query emits
    so the preview timeline lights correctly. Returns
    {"status": str|None, "current_stage": str|None}. Never raises: on absent
    engine / bad wid / not-found / DB error -> {"status": None,
    "current_stage": None} (mirrors resolve_ms02_pid_to_wids' degrade
    contract)."""
    empty = {"status": None, "current_stage": None}
    if engine is None or wid in (None, ""):
        return empty
    try:
        wid_int = int(wid)
    except (TypeError, ValueError):
        return empty
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        cur.execute(
            """
            WITH WorkitemCTE AS (
                SELECT
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
                    ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                FROM t_WorkItems twi
                INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                WHERE twi.ID = ?
            )
            SELECT Status, CurrentStage FROM WorkitemCTE WHERE rn = 1
            """,
            [wid_int],
        )
        row = cur.fetchone()
        if not row:
            return empty
        return {"status": row.Status, "current_stage": row.CurrentStage}
    except Exception as e:
        current_app.logger.error(f"resolve_octo_wid_stage({wid}): {e}")
        return empty
    finally:
        if conn is not None:
            conn.close()


def _resolve_octo_wid_stage_pg(engine, wid):
    """Postgres-dialect twin of resolve_octo_wid_stage, for the MS02 client's
    Azure Postgres runtime DB (same Octo schema, different dialect + case-
    preserved quoted identifiers -- see PostgresSource). Same {"status": None,
    "current_stage": None} degrade contract; never raises."""
    empty = {"status": None, "current_stage": None}
    if engine is None or wid in (None, ""):
        return empty
    try:
        wid_int = int(wid)
    except (TypeError, ValueError):
        return empty
    conn = None
    try:
        conn = engine.raw_connection()
        cur = conn.cursor()
        cur.execute(
            """
            WITH WorkitemCTE AS (
                SELECT
                    CASE
                        WHEN twi."Status" = 0 THEN 'Ready' WHEN twi."Status" = 5 THEN 'Done' ELSE 'In Progress'
                    END AS status,
                    CASE
                        WHEN twi."Status" = 5 THEN 'Delivery'
                        WHEN tai."ActivityInstanceName" LIKE '%%C+A%%' THEN 'Validation'
                        WHEN tai."ActivityInstanceName" LIKE '%%Export%%' OR tai."ActivityInstanceName" LIKE '%%Exp%%' THEN 'Delivery'
                        WHEN tai."ActivityInstanceName" LIKE '%%Import%%' OR tai."ActivityInstanceName" LIKE '%%Imp%%' THEN 'Import'
                        WHEN tai."ActivityInstanceName" LIKE '%%Extract%%' OR tai."ActivityInstanceName" LIKE '%%OCR%%' THEN 'Extraction'
                        WHEN tai."ActivityInstanceName" LIKE '%%Pause%%' OR tai."ActivityInstanceName" LIKE '%%Deletion%%' OR tai."ActivityInstanceName" LIKE '%%Lieferung%%' THEN 'Delivery'
                        ELSE 'Extraction'
                    END AS current_stage,
                    ROW_NUMBER() OVER (PARTITION BY twi."ID" ORDER BY twi."ModifiedAt" DESC) AS rn
                FROM "t_WorkItems" twi
                JOIN "t_ActivityInstances" tai ON twi."ActivityInstanceID" = tai."ID"
                WHERE twi."ID" = %s
            )
            SELECT status, current_stage FROM WorkitemCTE WHERE rn = 1
            """,
            [wid_int],
        )
        row = cur.fetchone()
        if not row:
            return empty
        return {"status": row[0], "current_stage": row[1]}
    except Exception as e:
        current_app.logger.error(f"_resolve_octo_wid_stage_pg({wid}): {e}")
        return empty
    finally:
        if conn is not None:
            conn.close()


def resolve_ms02_wids_to_pids(engine, specs, wids):
    """Inverse of resolve_ms02_pid_to_wids: map workitem ids -> their PID (col_pid)
    value, columnar. Used by the reverse 'In register' chip to learn each visible
    workitem's PID. Reuses the _MS02_IDENT guard + _as_workitem_ids.

    The ``wids`` themselves are ALWAYS integers -- the id-column comparison
    uses ``id_column_type`` (the 6th spec tuple element, #98 Task 12 --
    ProcessSource.IdColumnType, NOT the pid field's ColumnType used elsewhere
    in this module) to decide whether the WHERE/SELECT can stay bare/native-
    int (sargable) instead of ``::text``. A spec shorter than 6 elements
    falls back to ``id_column_type=None`` (always ``::text``).

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
        for spec in specs:
            table, id_col, pid_col, time_filter = spec[0], spec[1], spec[2], spec[3]
            id_column_type = spec[5] if len(spec) > 5 else None
            if not (table and id_col and pid_col):
                continue
            if not (_MS02_IDENT.match(id_col) and _MS02_IDENT.match(pid_col)):
                current_app.logger.error(
                    f"resolve_ms02_wids_to_pids: unsafe identifier {(id_col, pid_col)}"
                )
                continue
            if id_column_type in _MS02_INT_TYPES:
                sql = (
                    f'SELECT DISTINCT "{id_col}", "{pid_col}"::text'
                    f" FROM {table}"
                    f' WHERE "{id_col}" = ANY(%s)'
                )
                id_values = ids
            else:
                sql = (
                    f'SELECT DISTINCT "{id_col}", "{pid_col}"::text'
                    f" FROM {table}"
                    f' WHERE "{id_col}"::text = ANY(%s)'
                )
                id_values = [str(i) for i in ids]
            if time_filter:
                sql += f" AND {time_filter}"
            cur.execute(sql, [id_values])
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

    def process_of(self, workitem_id):
        """(ClientName, ProcessName) for a workitem, or None. PG dialect of the
        SqlServerSource.process_of entitlement lookup (#193)."""
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
            cur.execute(
                'SELECT tp."ClientName" AS clientname, tp."Name" AS name '
                'FROM "t_WorkItems" twi '
                'JOIN "t_ActivityInstances" tai ON twi."ActivityInstanceID" = tai."ID" '
                'JOIN "t_Processes" tp ON tp."ID" = tai."ProcessID" '
                'WHERE twi."ID" = %s LIMIT 1',
                (workitem_id,),
            )
            row = cur.fetchone()
            return (row.clientname, row.name) if row else None
        except Exception as e:
            current_app.logger.error(f"PostgresSource.process_of({workitem_id}): {e}")
            return None
        finally:
            conn.close()

    def _build_where(self, filt):
        pair_sql, pair_params = _pair_predicate(
            filt.client_process_pairs, 'tp."ClientName"', 'tp."Name"', "%s"
        )
        clauses = [f"({pair_sql})"]
        if filt.status_code != _STATUS_DELETED:
            clauses.append('twi."Status" <> 2')
        params = list(pair_params)
        # activity_ignore_csv is a literal "'A','B'" list (already escaped upstream).
        if filt.activity_ignore_csv:
            clauses.append(f'tai."ActivityInstanceName" NOT IN ({filt.activity_ignore_csv})')
        if filt.status_code is not None:
            # Same In-Progress bucket semantics as the SQL Server source.
            if filt.status_code == _STATUS_IN_PROGRESS:
                clauses.append('twi."Status" NOT IN (0, 5)')
            else:
                clauses.append('twi."Status" = %s')
                params.append(filt.status_code)
        if filt.search_id:
            # Prefix match, same semantics/reasoning as the SQL Server path above.
            clauses.append('CAST(twi."ID" AS TEXT) LIKE %s')
            params.append(str(filt.search_id).strip() + "%")
        if filt.start_date:
            clauses.append('twi."ModifiedAt" >= %s')
            params.append(filt.start_date)
        if filt.end_date:
            clauses.append('twi."ModifiedAt" < %s')
            params.append(filt.end_date)

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
        # Same empty-scope guard as the SQL Server source (see there).
        if not filt.client_process_pairs:
            return [], 0
        where, params = self._build_where(filt)
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)

            cte_sql = f"""
                WITH ranked AS (
                    SELECT
                        twi."ModifiedAt" AS modifiedat,
                        twi."ID" AS workitemid,
                        CASE
                            WHEN twi."Status" = 0 THEN 'Ready'
                            WHEN twi."Status" = 5 THEN 'Done'
                            WHEN twi."Status" = 2 THEN 'Deleted'
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
                ),
                latest AS (
                    SELECT * FROM ranked WHERE rn = 1
                )
            """
            # Stage is filtered post-dedup (on the workitem's latest activity
            # row only), so it's applied against `latest`, not `where`.
            stage_clause = "WHERE currentstage = %s" if filt.stage else ""
            stage_params = [filt.stage] if filt.stage else []

            # Same relevance-first ordering as the SQL Server source's
            # list_workitems -- see the comment there.
            order_clause = (
                "ORDER BY LENGTH(workitemid::text) ASC, modifiedat DESC"
                if filt.search_id
                else "ORDER BY modifiedat DESC"
            )

            cur.execute(
                cte_sql + f"SELECT COUNT(*) FROM latest {stage_clause}",
                [*params, *stage_params],
            )
            total = cur.fetchone()[0] or 0

            cur.execute(
                cte_sql
                + f"""
                SELECT modifiedat, workitemid, status, currentstage
                FROM latest {stage_clause}
                {order_clause}
                LIMIT %s OFFSET %s
                """,
                [*params, *stage_params, limit, offset],
            )
            rows = [
                {
                    "modifiedat": r.modifiedat,
                    "workitemid": r.workitemid,
                    "status": r.status,
                    "current_stage": r.currentstage,
                    "client": self.code,
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

        return rows, total

    def recent_rows(self, pairs, activity_ignore_csv, top=3):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
            pair_sql, pair_params = _pair_predicate(pairs, 'tp."ClientName"', 'tp."Name"', "%s")
            clauses = [
                'twi."Status" <> 2',
                f"({pair_sql})",
            ]
            params = list(pair_params)
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

    def backlog_count(self, pairs):
        conn = self.engine.raw_connection()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.NamedTupleCursor)
            pair_sql, pair_params = _pair_predicate(pairs, 'p."ClientName"', 'p."Name"', "%s")
            cur.execute(
                f"""
                SELECT COUNT(*) FROM "t_WorkItems" w
                LEFT JOIN "t_ActivityInstances" a ON a."ID" = w."ActivityInstanceID"
                LEFT JOIN "t_Processes" p ON p."ID" = a."ProcessID"
                LEFT JOIN "t_ActivityTypes" act ON act."ID" = a."ActivityTypeID"
                WHERE ({pair_sql}) AND act."Name" = 'C+A'
                """,
                pair_params,
            )
            return cur.fetchone()[0] or 0
        except Exception as e:
            current_app.logger.error(f"PostgresSource.backlog_count: {e}")
            return 0
        finally:
            conn.close()


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
        rows = cur.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            current_app.logger.error(
                f"WorkitemSourceCache lookup({workitem_id}): {len(rows)} rows "
                "-- ambiguous (compound PK collision), forcing re-probe."
            )
            return None
        return rows[0][0]
    except Exception as e:
        current_app.logger.error(f"WorkitemSourceCache lookup({workitem_id}): {e}")
        return None
    finally:
        conn.close()


def _cache_lookup_many(workitem_ids):
    """Batched cache lookup: one (chunked) query instead of one round-trip per
    id. Returns {id_str: client_code} for unambiguous hits only -- an id with
    more than one cached row is OMITTED (ambiguous -> caller re-probes via
    get_source_for_workitem, same fail-safe as _cache_lookup)."""
    ids = [str(w) for w in workitem_ids]
    if not ids:
        return {}
    result = {}
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        seen_counts = {}
        for i in range(0, len(ids), 1000):
            chunk = ids[i : i + 1000]
            placeholders = ",".join("?" for _ in chunk)
            cur.execute(
                f"SELECT WorkItemID, ClientCode FROM WorkitemSourceCache "
                f"WHERE WorkItemID IN ({placeholders})",
                chunk,
            )
            for wid, client_code in cur.fetchall():
                wid = str(wid)
                seen_counts[wid] = seen_counts.get(wid, 0) + 1
                result[wid] = client_code
        ambiguous = [wid for wid, count in seen_counts.items() if count > 1]
        for wid in ambiguous:
            current_app.logger.error(
                f"WorkitemSourceCache lookup_many({wid}): {seen_counts[wid]} rows "
                "-- ambiguous (compound PK collision), forcing re-probe."
            )
            result.pop(wid, None)
        return result
    except Exception as e:
        current_app.logger.error(f"WorkitemSourceCache lookup_many: {e}")
        return {}
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
            ON tgt.WorkItemID = src.WorkItemID AND tgt.ClientCode = src.ClientCode
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


def get_source_for_workitem(workitem_id, client_hint=None, sources=None):
    """Resolve which client owns ``workitem_id``.

    Order of trust (collision fail-safe):
    1. Explicit ``client_hint`` from the caller (the list row knows its own
       client) — authoritative, and the ONLY way to disambiguate a colliding id.
    2. Cache hit.
    3. Probe ALL sources, INCLUDING the default one. Exactly one claimant ->
       that client (cache it). Zero -> 'default'.
    4. FAIL-SAFE: more than one claimant means id spaces overlap — do NOT guess
       and do NOT cache; log loudly and fall back to 'default'.

    The default source used to be excluded from the probe, so a default/MS02
    collision (1216 such ids on INT) looked like a single MS02 claim and was
    cached permanently — serving the other client's document for that id.

    ``sources``: optional pre-built ``active_sources()`` list. Callers that
    already hold one (e.g. fetch_merged_page's warm-cache loop, probing every
    non-default row on the page) should pass it through instead of paying for
    a fresh set of source instances per probed row. Defaults to a fresh
    ``active_sources()`` call when omitted, unchanged from before.
    """
    if client_hint and client_hint in CLIENTS:
        return client_hint

    cached = _cache_lookup(workitem_id)
    if cached:
        return cached

    claimers = []
    for src in sources if sources is not None else active_sources():
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


def get_domain_for_workitem(workitem_id, client_hint=None):
    """Octo domain for a workitem's owning client. Real replacement for the
    former octo.py stub. ``client_hint`` comes from the list row the user
    actually clicked, and is what makes colliding ids resolvable."""
    code = get_source_for_workitem(workitem_id, client_hint=client_hint)
    client = CLIENTS.get(code) or CLIENTS["default"]
    return client.octo_domain


def source_for(code):
    """Active source instance for a client code, or None."""
    for src in active_sources():
        if src.code == code:
            return src
    return None


def process_pair_for_workitem(workitem_id, client_hint=None):
    """(ClientName, ProcessName) of a workitem in the source a detail request
    will actually read (same client_hint routing as get_domain_for_workitem),
    or None if it can't be resolved. Feeds the detail-access entitlement check
    (#193) — the caller must hold a grant for this exact pair."""
    code = get_source_for_workitem(workitem_id, client_hint=client_hint)
    src = source_for(code)
    return src.process_of(workitem_id) if src else None


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
    merged = merge_sorted_rows(per_source_rows, search_id=filt.search_id)
    page = merged[offset : offset + limit]

    # Warm the routing cache for non-default rows on this page. First, ONE
    # batched cache lookup for every non-default id on the page (instead of
    # up to `limit` sequential round-trips). Ids that come back missing --
    # not cached yet, or ambiguous per _cache_lookup_many's own fail-safe --
    # fall through to get_source_for_workitem's collision fail-safe (not a
    # direct _cache_store) so a colliding id -- claimed by more than one
    # source -- is left uncached instead of being pinned to whichever
    # client's page happened to list it first during this warm pass. Pass
    # the ``sources`` list this function already built above -- avoids
    # get_source_for_workitem constructing a second fresh set of source
    # instances (2 extra objects) for every non-default row on the page; the
    # live has_workitem probes themselves are unchanged, since
    # list_workitems' permission/date/status-filtered, offset+limit-capped
    # rows are not proof of exclusive ownership the way an unscoped
    # has_workitem check is -- skipping the probe based on this page's own
    # row shape would risk under-detecting a real collision whose twin row
    # didn't happen to surface in this particular filtered fetch.
    non_default_ids = [r["workitemid"] for r in page if r["client"] != "default"]
    cached_map = _cache_lookup_many(non_default_ids)
    for wid in non_default_ids:
        if str(wid) not in cached_map:
            get_source_for_workitem(wid, sources=sources)

    return page, total, degraded


def recent_activity_rows(pairs, activity_ignore_csv, top=3):
    """Top-N most recently modified workitems across all sources, merged.
    Each row: {id, modifiedat, process, client}.

    ``pairs``: granted [(client, process), ...] -- see WorkitemFilter.
    client_process_pairs for why this must never be split into independent
    client/process lists."""
    out = []
    for src in active_sources():
        try:
            out.extend(src.recent_rows(pairs, activity_ignore_csv, top))
        except Exception as e:
            current_app.logger.error(f"recent_activity_rows {src.code}: {e}")
    out.sort(key=lambda r: r["modifiedat"], reverse=True)
    return out[:top]


def total_backlog_count(pairs):
    """Sum the C+A backlog count across all active sources (resilient).

    ``pairs``: granted [(client, process), ...] -- see WorkitemFilter.
    client_process_pairs for why this must never be split into independent
    client/process lists."""
    total = 0
    for src in active_sources():
        try:
            total += src.backlog_count(pairs)
        except Exception as e:
            current_app.logger.error(f"total_backlog_count {src.code}: {e}")
    return total
