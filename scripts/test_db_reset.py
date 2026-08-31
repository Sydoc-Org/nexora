"""Reset NEXORA_TEST to a known state: wipes it, then applies sql/test/schema.sql
and sql/test/seed.sql.

Uses pyodbc instead of sqlcmd so it runs anywhere pyodbc does (i.e. anywhere
nexora itself runs) without needing SQL Server Command Line Tools installed.

Reads connection info from env/TEST.env. Idempotent.

Usage:
    python scripts/test_db_reset.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pyodbc

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV = REPO_ROOT / "env" / "TEST.env"
SCHEMA_SQL = REPO_ROOT / "sql" / "test" / "schema.sql"
SEED_SQL = REPO_ROOT / "sql" / "test" / "seed.sql"

# Match lines that are JUST `GO` (case-insensitive), with optional whitespace.
# Splitting on this matches sqlcmd's batch-separator behaviour.
GO_SPLIT = re.compile(r"^\s*GO\s*$", re.MULTILINE | re.IGNORECASE)


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# Everything NEXORA_TEST needs is recreated from schema.sql + seed.sql, so anything
# still standing when a reset starts is stale -- an object schema.sql stopped
# creating, or a table a parallel session applied its own migration for. Dropping
# the lot is what makes this script's "known state" claim true: a hand-maintained
# FK-safe DROP order inside schema.sql cannot know about tables it has never heard
# of, and has wedged the reset twice (dbo.Clients / dbo.KundenmagazinIssue* holding
# FKs into dbo.Organizations was the latest).
WIPE_SQL = """
DECLARE @sql nvarchar(max);

SET @sql = N'';
SELECT @sql = @sql + N'ALTER TABLE ' + QUOTENAME(SCHEMA_NAME(t.schema_id)) + N'.'
       + QUOTENAME(t.name) + N' DROP CONSTRAINT ' + QUOTENAME(fk.name) + N';'
FROM sys.foreign_keys fk
JOIN sys.tables t ON t.object_id = fk.parent_object_id;
EXEC sp_executesql @sql;

SET @sql = N'';
SELECT @sql = @sql + N'DROP VIEW ' + QUOTENAME(SCHEMA_NAME(schema_id)) + N'.'
       + QUOTENAME(name) + N';'
FROM sys.views WHERE is_ms_shipped = 0;
EXEC sp_executesql @sql;

SET @sql = N'';
SELECT @sql = @sql + N'DROP TABLE ' + QUOTENAME(SCHEMA_NAME(schema_id)) + N'.'
       + QUOTENAME(name) + N';'
FROM sys.tables WHERE is_ms_shipped = 0;
EXEC sp_executesql @sql;

SET @sql = N'';
SELECT @sql = @sql + N'DROP ' + CASE type WHEN 'P' THEN N'PROCEDURE ' ELSE N'FUNCTION ' END
       + QUOTENAME(SCHEMA_NAME(schema_id)) + N'.' + QUOTENAME(name) + N';'
FROM sys.objects WHERE type IN ('P', 'FN', 'IF', 'TF') AND is_ms_shipped = 0;
EXEC sp_executesql @sql;
"""


def wipe_database(cursor: pyodbc.Cursor) -> tuple[int, int]:
    """Drop every user object. Re-checks DB_NAME() first: the caller's TEST.env
    guard reads a file, this reads the connection actually about to be emptied."""
    live = cursor.execute("SELECT DB_NAME()").fetchone()
    name = live[0] if live else None
    if name != "NEXORA_TEST":
        raise RuntimeError(f"refusing to wipe '{name}': connection is not NEXORA_TEST")
    counts = cursor.execute(
        "SELECT (SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped = 0),"
        " (SELECT COUNT(*) FROM sys.objects WHERE type IN ('P','FN','IF','TF','V')"
        "  AND is_ms_shipped = 0)"
    ).fetchone()
    cursor.execute(WIPE_SQL)
    while cursor.nextset():
        pass
    return int(counts[0]), int(counts[1])


def execute_sql_file(cursor: pyodbc.Cursor, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    batches = [b.strip() for b in GO_SPLIT.split(sql)]
    batches = [b for b in batches if b]
    for i, batch in enumerate(batches, start=1):
        try:
            cursor.execute(batch)
            # Drain any result sets so the next execute doesn't trip
            while cursor.nextset():
                pass
        except pyodbc.Error as e:
            raise RuntimeError(
                f"{path.name}: batch {i}/{len(batches)} failed.\n"
                f"--- SQL ---\n{batch}\n--- error ---\n{e}"
            ) from e


def _pick_sqlserver_driver() -> str | None:
    """Best installed SQL Server ODBC driver, newest first.

    Mirrors what a developer would put in DB_ODBC_DRIVER by hand; the legacy
    "SQL Server" driver is last because it lacks Encrypt/TrustServerCertificate
    support (see the _TLS_SUFFIX note in nx_lib/db.py).
    """
    installed = pyodbc.drivers()
    for candidate in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server",
    ):
        if candidate in installed:
            return candidate
    return None


def main() -> int:
    if not TEST_ENV.exists():
        print(
            f"env/TEST.env not found at {TEST_ENV}. "
            "Copy env/TEST.env.example to env/TEST.env and fill in values.",
            file=sys.stderr,
        )
        return 1

    env = parse_env(TEST_ENV)
    server = env.get("DB_SERVER_PRD")
    uid = env.get("DB_UID")
    pwd = env.get("DB_PWD")
    db = env.get("DB_NEXORA")

    missing = [
        k
        for k, v in [("DB_SERVER_PRD", server), ("DB_UID", uid), ("DB_PWD", pwd), ("DB_NEXORA", db)]
        if not v
    ]
    if missing:
        print(f"TEST.env is missing: {', '.join(missing)}", file=sys.stderr)
        return 1

    if db != "NEXORA_TEST":
        print(
            f"Refusing to run: DB_NEXORA in TEST.env must be 'NEXORA_TEST', got '{db}'.",
            file=sys.stderr,
        )
        return 1

    for p in (SCHEMA_SQL, SEED_SQL):
        if not p.exists():
            print(f"Missing: {p}", file=sys.stderr)
            return 1

    # Use the same driver nexora itself uses -- DB_ODBC_DRIVER from the env file,
    # exactly like nx_lib/db.py, falling back to whatever SQL Server driver is
    # actually installed. This used to hardcode "ODBC Driver 17 for SQL Server",
    # which made the script unusable on any box that ships 18 (or only the legacy
    # "SQL Server") even though its docstring promises it runs anywhere pyodbc
    # does. autocommit so each batch commits immediately (schema.sql can't run
    # inside an explicit transaction anyway because it does CREATE/DROP).
    driver = env.get("DB_ODBC_DRIVER") or _pick_sqlserver_driver()
    if not driver:
        print(
            "No SQL Server ODBC driver found. Install one, or set DB_ODBC_DRIVER "
            f"in env/TEST.env. Available: {pyodbc.drivers()}",
            file=sys.stderr,
        )
        return 1

    # Driver 17/18 understand (and 18 defaults to requiring) TLS, and reject a
    # self-signed server cert unless told to trust it. The legacy "SQL Server"
    # driver errors on these keywords outright, so they're only added for the
    # modern ones -- same conditional as _TLS_SUFFIX in nx_lib/db.py.
    tls = "Encrypt=yes;TrustServerCertificate=yes;" if driver.startswith("ODBC Driver") else ""
    conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};{tls}"
    print(f"Using ODBC driver: {driver}")
    conn = pyodbc.connect(conn_str, autocommit=True)
    try:
        cursor = conn.cursor()
        tables, progs = wipe_database(cursor)
        print(f"Wiped {db} on {server} ({tables} tables, {progs} views/procs/functions)")
        print(f"Applying schema to {db} on {server}...")
        execute_sql_file(cursor, SCHEMA_SQL)
        print(f"Applying seed to {db} on {server}...")
        execute_sql_file(cursor, SEED_SQL)
    finally:
        conn.close()

    print("NEXORA_TEST reset complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
