"""Resolve native column types for the normalized mapping registry (#98 Task 11).

Reads (read-only, never writes):
    - NexoraDB dbo.ProcessSources / dbo.ProcessFieldMappings (migration 0074) --
      the rows to resolve types FOR.
    - StatisticsDB INFORMATION_SCHEMA.COLUMNS -- native SQL Server types for
      every non-MS02 ("default" client) ProcessSource's table.
    - the MS02 doc-field Postgres DB's information_schema.columns -- native PG
      types for MS02-client ProcessSource tables.

Prints a complete migration file body of guarded UPDATE statements to stdout.
Unresolvable columns (table/column missing from the target DB's introspection)
become SQL comments, NEVER an UPDATE -- leaving ColumnType/IdColumnType NULL,
which keeps the legacy CAST/::text predicate path (see 0074/0075 comments).

The id column is parsed out of ProcessSources.JoinCondition the SAME way the
runtime does at query time (nx_lib/workitem_sources.py:_ms02_id_column) so the
seeded IdColumnType corresponds to the column the runtime actually looks up.

Usage:
    python scripts/seed_column_types.py --env INT > sql/_migrations/NexoraDB/0076_seed_column_types.sql

This script does not write the migration file itself -- review stdout, then
save it and apply via scripts/db-migrate.py as usual.
"""

import argparse
import datetime
import importlib.util
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Same JoinCondition/alias regex the runtime uses -- nx_lib/workitem_sources.py
# _ms02_id_column(). Duplicated here (not imported) because this script runs
# standalone against nx_lib/config.py without a Flask app context.
_ID_COL_RE = None  # built per-alias below


def _id_column(join_condition, alias):
    """Mirror of nx_lib.workitem_sources._ms02_id_column -- keep in sync."""
    if not join_condition or not alias:
        return None
    for part in re.split(r"\s*=\s*", join_condition.strip()):
        m = re.match(rf"^{re.escape(alias)}\.(\w+)$", part.strip(), re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def load_nexora_config(env_name: str):
    """Load nx_lib/config.py directly, same pattern as scripts/db-migrate.py
    and sql/sync-from-db.py."""
    os.environ["ENVIRONMENT"] = env_name
    spec = importlib.util.spec_from_file_location(
        "_nexora_config_for_seed_column_types",
        str(REPO_ROOT / "nx_lib" / "config.py"),
    )
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return cfg


def connect_mssql(server, db, uid, pwd, driver):
    import pyodbc

    return pyodbc.connect(
        f"DRIVER={{{driver}}};"
        f"SERVER={server},1433;"
        f"DATABASE={db};"
        f"UID={uid};"
        f"PWD={pwd};"
    )


def connect_pg(host, db, uid, pwd, port, sslmode):
    import psycopg2

    return psycopg2.connect(
        host=host,
        dbname=db,
        user=uid,
        password=pwd,
        port=int(port),
        sslmode=sslmode,
    )


def load_stat_columns(conn):
    """{TABLE_NAME (lower) -> {COLUMN_NAME (lower) -> DATA_TYPE}} from
    StatisticsDB INFORMATION_SCHEMA.COLUMNS (dbo schema only)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'dbo'"
    )
    out = {}
    for table_name, column_name, data_type in cur.fetchall():
        out.setdefault(table_name.lower(), {})[column_name.lower()] = data_type
    cur.close()
    return out


def load_pg_columns(conn):
    """{table_name (lower) -> {column_name (lower) -> data_type}} from the
    MS02 doc-field DB's information_schema.columns (public schema only)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    )
    out = {}
    for table_name, column_name, data_type in cur.fetchall():
        out.setdefault(table_name.lower(), {})[column_name.lower()] = data_type
    cur.close()
    return out


def strip_dbo_prefix(table):
    """'dbo.Foo' -> 'Foo'; leaves other tables (e.g. already-bare) unchanged."""
    if not table:
        return table
    if table.lower().startswith("dbo."):
        return table[4:]
    return table


def strip_pg_quoting(table):
    """'public."DossierStatistik"' -> 'DossierStatistik'; also handles a bare
    quoted or unquoted name."""
    if not table:
        return table
    t = table.strip()
    if t.lower().startswith("public."):
        t = t[len("public.") :]
    t = t.strip('"')
    return t


def sql_escape(s):
    return s.replace("'", "''")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="INT", help="ENVIRONMENT to load env/<ENV>.env for")
    args = parser.parse_args()

    cfg = load_nexora_config(args.env)

    # NexoraDB: read ProcessSources + ProcessFieldMappings (0074 registry).
    nexora_conn = connect_mssql(
        cfg.DB_SERVER_PRD, cfg.DB_NEXORA, cfg.DB_UID, cfg.DB_PWD, cfg.DB_ODBC_DRIVER
    )
    cur = nexora_conn.cursor()
    cur.execute(
        "SELECT ClientCode, ProcessName, TableName, TableAlias, JoinCondition "
        "FROM dbo.ProcessSources"
    )
    sources = cur.fetchall()
    cur.execute(
        "SELECT ClientCode, ProcessName, FieldKey, ColumnName FROM dbo.ProcessFieldMappings"
    )
    mappings = cur.fetchall()
    cur.close()
    nexora_conn.close()

    # Target DBs: StatisticsDB (SQL Server, "default" / non-MS02 clients) and
    # the MS02 doc-field Postgres DB (client "ms02"). Both read-only
    # introspection queries -- never write to either.
    stat_conn = connect_mssql(
        cfg.DB_SERVER_PRD, cfg.DB_STATISTICS, cfg.DB_UID, cfg.DB_PWD, cfg.DB_ODBC_DRIVER
    )
    stat_columns = load_stat_columns(stat_conn)
    stat_conn.close()

    pg_columns = {}
    if (
        cfg.MS02_DOCFIELDS_DB_HOST
        and cfg.MS02_DOCFIELDS_DB_NAME
        and cfg.MS02_DOCFIELDS_DB_USER
        and cfg.MS02_DOCFIELDS_DB_PWD
    ):
        pg_conn = connect_pg(
            cfg.MS02_DOCFIELDS_DB_HOST,
            cfg.MS02_DOCFIELDS_DB_NAME,
            cfg.MS02_DOCFIELDS_DB_USER,
            cfg.MS02_DOCFIELDS_DB_PWD,
            cfg.MS02_DOCFIELDS_DB_PORT,
            cfg.MS02_DB_SSLMODE,
        )
        pg_columns = load_pg_columns(pg_conn)
        pg_conn.close()
    else:
        print(
            "-- WARNING: MS02_DOCFIELDS_DB_* not configured; MS02 client rows "
            "left unresolved (comments only).",
            file=sys.stderr,
        )

    def columns_for(client, table):
        """Resolve the {column_name(lower): data_type} map for a
        (client, table) ProcessSources row, or None if the table itself is
        unresolvable in the target DB."""
        if client == "ms02":
            bare = strip_pg_quoting(table)
            return pg_columns.get((bare or "").lower())
        bare = strip_dbo_prefix(table)
        return stat_columns.get((bare or "").lower())

    # text/ntext are deprecated LOB types SQL Server rejects for bare
    # =/<> comparison (error 402/8180) -- migration 0077 had to revert one
    # such column's seeded ColumnType back to NULL after it broke doc-field
    # search. Never seed these; leave them UNRESOLVED (comment only) so the
    # legacy CAST fallback keeps handling them.
    unsafe_types = {"text", "ntext"}

    resolved = 0
    unresolved = 0

    lines = []
    lines.append("-- 0076: seed ColumnType / IdColumnType from live target DBs (#98).")
    lines.append(
        "-- Generated by scripts/seed_column_types.py against StatisticsDB "
        "INFORMATION_SCHEMA.COLUMNS (default client) and the MS02 doc-field "
        "Postgres DB's information_schema.columns (ms02 client), read-only."
    )
    lines.append(
        "-- Unresolvable table/column pairs are left as comments (NULL stays "
        "NULL), which keeps the legacy CAST/::text predicate path (Task 12)."
    )
    lines.append(f"-- Generated: {datetime.datetime.now(datetime.UTC).isoformat()}")
    lines.append("")

    # IdColumnType on ProcessSources, derived from JoinCondition/TableAlias the
    # same way the runtime resolves the id column at query time.
    lines.append("-- ProcessSources.IdColumnType")
    for client, process, table, alias, join_condition in sources:
        id_col = _id_column(join_condition, alias)
        cols = columns_for(client, table)
        data_type = None
        if id_col and cols is not None:
            data_type = cols.get(id_col.lower())
        if data_type and data_type.lower() not in unsafe_types:
            resolved += 1
            lines.append(
                "UPDATE dbo.ProcessSources SET IdColumnType = "
                f"'{sql_escape(data_type)}' WHERE ClientCode = '{sql_escape(client)}' "
                f"AND ProcessName = '{sql_escape(process)}';"
            )
        else:
            unresolved += 1
            reason = (
                "no id column parsed from JoinCondition"
                if not id_col
                else (
                    "target table not found"
                    if cols is None
                    else (
                        f"unsafe type {data_type!r} (text/ntext reject bare =/<>)"
                        if data_type and data_type.lower() in unsafe_types
                        else "column not found in target table"
                    )
                )
            )
            lines.append(
                f"-- UNRESOLVED IdColumnType: client={client} process={process} "
                f"table={table!r} id_col={id_col!r} ({reason})"
            )
    lines.append("GO")
    lines.append("")

    # ColumnType on ProcessFieldMappings.
    lines.append("-- ProcessFieldMappings.ColumnType")
    source_table = {(c, p): t for c, p, t, a, j in sources}
    for client, process, field_key, column_name in mappings:
        table = source_table.get((client, process))
        cols = columns_for(client, table)
        data_type = cols.get((column_name or "").lower()) if cols is not None else None
        if data_type and data_type.lower() not in unsafe_types:
            resolved += 1
            lines.append(
                "UPDATE dbo.ProcessFieldMappings SET ColumnType = "
                f"'{sql_escape(data_type)}' WHERE ClientCode = '{sql_escape(client)}' "
                f"AND ProcessName = '{sql_escape(process)}' "
                f"AND FieldKey = '{sql_escape(field_key)}';"
            )
        else:
            unresolved += 1
            reason = (
                "source table not found"
                if table is None
                else (
                    "target table not found"
                    if cols is None
                    else (
                        f"unsafe type {data_type!r} (text/ntext reject bare =/<>)"
                        if data_type and data_type.lower() in unsafe_types
                        else "column not found in target table"
                    )
                )
            )
            lines.append(
                f"-- UNRESOLVED ColumnType: client={client} process={process} "
                f"field_key={field_key} table={table!r} column={column_name!r} ({reason})"
            )
    lines.append("GO")

    print("\n".join(lines))
    print(f"-- resolved={resolved} unresolved={unresolved}", file=sys.stderr)


if __name__ == "__main__":
    main()
