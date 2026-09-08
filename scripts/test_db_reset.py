"""Reset a NEXORA_TEST* database to a known state: wipes it, then applies
sql/test/schema.sql and sql/test/seed.sql.

Uses pyodbc instead of sqlcmd so it runs anywhere pyodbc does (i.e. anywhere
nexora itself runs) without needing SQL Server Command Line Tools installed.

Reads connection info from env/TEST.env; a DB_NEXORA in the process
environment overrides the file's database name. Idempotent.

pytest does not use the shared NEXORA_TEST any more: tests/conftest.py
creates a private NEXORA_TEST_<user>_<pid> database per run (create + schema
+ seed is ~1.5 s) and drops it at the end, so parallel runs never meet and
never wait on each other (#235). This script still resets the shared one for
hand-driven TEST servers.

Usage:
    python scripts/test_db_reset.py           # reset NEXORA_TEST (or $DB_NEXORA)
    python scripts/test_db_reset.py --prune   # drop per-run DBs older than 3 h
"""

from __future__ import annotations

import getpass
import os
import re
import sys
from pathlib import Path

import pyodbc

REPO_ROOT = Path(__file__).resolve().parents[1]

# Run as a script (`python scripts/test_db_reset.py`) only scripts/ lands on
# sys.path, not the repo root -- but tests/conftest.py imports this module as
# scripts.test_db_reset. Put the root on the path so one import form works both
# ways rather than duplicating the lock protocol in two places.
sys.path.insert(0, str(REPO_ROOT))

from scripts import db_lock  # noqa: E402

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
    if not is_test_db(name):
        raise RuntimeError(f"refusing to wipe '{name}': not a {TEST_DB_PREFIX}* database")
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


# Every database this module will create, wipe or drop carries this prefix --
# the guard that keeps a mis-set env file from emptying INT or PROD.
TEST_DB_PREFIX = "NEXORA_TEST"
# Per-run databases live ~15 min at most (a full e2e run); anything older is an
# orphan from a killed run.
PRUNE_AFTER_HOURS = 3


def is_test_db(name: str | None) -> bool:
    return name is not None and name.upper().startswith(TEST_DB_PREFIX)


def fresh_db_name() -> str:
    """NEXORA_TEST_<user>_<pid>: unique per process on one machine, and readable
    in sys.databases when hunting an orphan."""
    user = re.sub(r"[^A-Za-z0-9]", "", getpass.getuser()) or "anon"
    return f"{TEST_DB_PREFIX}_{user}_{os.getpid()}"


def create_database(name: str) -> None:
    if not is_test_db(name):
        raise RuntimeError(f"refusing to create '{name}': not a {TEST_DB_PREFIX}* name")
    with connect_test_db("master") as conn:
        conn.cursor().execute(f"IF DB_ID(?) IS NULL CREATE DATABASE [{name}]", name)


def drop_database(name: str) -> None:
    if not is_test_db(name) or name.upper() == TEST_DB_PREFIX:
        raise RuntimeError(f"refusing to drop '{name}': only per-run {TEST_DB_PREFIX}_* databases")
    with connect_test_db("master") as conn:
        # SINGLE_USER kicks the app's own pooled connections; a plain DROP
        # would fail with "database in use" while the e2e server winds down.
        conn.cursor().execute(
            f"IF DB_ID(?) IS NOT NULL BEGIN "
            f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
            f"DROP DATABASE [{name}]; END",
            name,
        )


def prune_databases(older_than_hours: float = PRUNE_AFTER_HOURS) -> list[str]:
    """Drop per-run databases a killed run left behind. Returns their names."""
    with connect_test_db("master") as conn:
        rows = (
            conn.cursor()
            .execute(
                "SELECT name FROM sys.databases WHERE name LIKE ? "
                "AND create_date < DATEADD(minute, ?, SYSDATETIME())",
                f"{TEST_DB_PREFIX}[_]%",  # [_]: a literal underscore in LIKE
                -int(older_than_hours * 60),
            )
            .fetchall()
        )
    names = [r[0] for r in rows]
    for n in names:
        drop_database(n)
    return names


class TestDbUnavailableError(RuntimeError):
    """env/TEST.env is missing, misconfigured, or no SQL Server ODBC driver exists.

    Carries a printable reason -- callers surface str(e) rather than a traceback.
    """


def connect_test_db(db: str | None = None) -> pyodbc.Connection:
    """Autocommit pyodbc connection to a NEXORA_TEST* database, built from
    env/TEST.env. `db` defaults to $DB_NEXORA, then the file's DB_NEXORA;
    pass "master" to create or drop databases.

    Shared with tests/conftest.py so the suite reaches the same server through
    the same driver selection as the reset.
    """
    if not TEST_ENV.exists():
        raise TestDbUnavailableError(
            f"env/TEST.env not found at {TEST_ENV}. "
            "Copy env/TEST.env.example to env/TEST.env and fill in values."
        )

    env = parse_env(TEST_ENV)
    server = env.get("DB_SERVER_PRD")
    uid = env.get("DB_UID")
    pwd = env.get("DB_PWD")
    db = db or os.environ.get("DB_NEXORA") or env.get("DB_NEXORA")

    missing = [
        k
        for k, v in [("DB_SERVER_PRD", server), ("DB_UID", uid), ("DB_PWD", pwd), ("DB_NEXORA", db)]
        if not v
    ]
    if missing:
        raise TestDbUnavailableError(f"TEST.env is missing: {', '.join(missing)}")

    if db != "master" and not is_test_db(db):
        raise TestDbUnavailableError(
            f"Refusing to run: DB_NEXORA must start with '{TEST_DB_PREFIX}', got '{db}'."
        )

    # Use the same driver nexora itself uses -- DB_ODBC_DRIVER from the env file,
    # exactly like nx_lib/db.py, falling back to whatever SQL Server driver is
    # actually installed. This used to hardcode "ODBC Driver 17 for SQL Server",
    # which made the script unusable on any box that ships 18 (or only the legacy
    # "SQL Server") even though its docstring promises it runs anywhere pyodbc
    # does. autocommit so each batch commits immediately (schema.sql can't run
    # inside an explicit transaction anyway because it does CREATE/DROP).
    driver = env.get("DB_ODBC_DRIVER") or _pick_sqlserver_driver()
    if not driver:
        raise TestDbUnavailableError(
            "No SQL Server ODBC driver found. Install one, or set DB_ODBC_DRIVER "
            f"in env/TEST.env. Available: {pyodbc.drivers()}"
        )

    # Driver 17/18 understand (and 18 defaults to requiring) TLS, and reject a
    # self-signed server cert unless told to trust it. The legacy "SQL Server"
    # driver errors on these keywords outright, so they're only added for the
    # modern ones -- same conditional as _TLS_SUFFIX in nx_lib/db.py.
    tls = "Encrypt=yes;TrustServerCertificate=yes;" if driver.startswith("ODBC Driver") else ""
    conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};{tls}"
    return pyodbc.connect(conn_str, autocommit=True)


def apply_schema_and_seed(cursor: pyodbc.Cursor) -> None:
    execute_sql_file(cursor, SCHEMA_SQL)
    execute_sql_file(cursor, SEED_SQL)


def main() -> int:
    if "--prune" in sys.argv[1:]:
        try:
            dropped = prune_databases()
        except (TestDbUnavailableError, pyodbc.Error) as e:
            print(str(e), file=sys.stderr)
            return 1
        print(
            f"Dropped {len(dropped)} orphaned per-run test database(s): {', '.join(dropped) or '-'}"
        )
        return 0

    for path in (SCHEMA_SQL, SEED_SQL):
        if not path.exists():
            print(f"Missing: {path}", file=sys.stderr)
            return 1

    try:
        conn = connect_test_db()
    except TestDbUnavailableError as e:
        print(str(e), file=sys.stderr)
        return 1
    except pyodbc.Error as e:
        print(f"Could not connect to NEXORA_TEST: {e}", file=sys.stderr)
        return 1

    try:
        # Wiping and re-seeding while someone else's suite is mid-run is exactly
        # what #235 is about, so queue behind them rather than pull dbo.Users out
        # from under a running test.
        with db_lock.hold(conn, label="test_db_reset"):
            cursor = conn.cursor()
            server, name = cursor.execute("SELECT @@SERVERNAME, DB_NAME()").fetchone()
            tables, progs = wipe_database(cursor)
            print(f"Wiped {name} on {server} ({tables} tables, {progs} views/procs/functions)")
            print(f"Applying schema + seed to {name} on {server}...")
            apply_schema_and_seed(cursor)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("Reset complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
