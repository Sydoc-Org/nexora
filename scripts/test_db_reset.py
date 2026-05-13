"""Reset NEXORA_TEST to a known state: applies sql/test/schema.sql then sql/test/seed.sql.

Uses pyodbc instead of sqlcmd so it runs anywhere pyodbc does (i.e. anywhere
nexora itself runs) without needing SQL Server Command Line Tools installed.

Reads connection info from TEST.env at the repo root. Idempotent.

Usage:
    python scripts/test_db_reset.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pyodbc


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV = REPO_ROOT / "TEST.env"
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


def main() -> int:
    if not TEST_ENV.exists():
        print(f"TEST.env not found at {TEST_ENV}. Copy TEST.env.example and fill in values.",
              file=sys.stderr)
        return 1

    env = parse_env(TEST_ENV)
    server = env.get("DB_SERVER_PRD")
    uid = env.get("DB_UID")
    pwd = env.get("DB_PWD")
    db = env.get("DB_NEXORA")

    missing = [k for k, v in [("DB_SERVER_PRD", server), ("DB_UID", uid),
                              ("DB_PWD", pwd), ("DB_NEXORA", db)] if not v]
    if missing:
        print(f"TEST.env is missing: {', '.join(missing)}", file=sys.stderr)
        return 1

    if db != "NEXORA_TEST":
        print(f"Refusing to run: DB_NEXORA in TEST.env must be 'NEXORA_TEST', got '{db}'.",
              file=sys.stderr)
        return 1

    for p in (SCHEMA_SQL, SEED_SQL):
        if not p.exists():
            print(f"Missing: {p}", file=sys.stderr)
            return 1

    # Use the same driver nexora itself uses. autocommit so each batch commits
    # immediately (schema.sql can't run inside an explicit transaction anyway
    # because it does CREATE/DROP).
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server};DATABASE={db};UID={uid};PWD={pwd};"
    )
    conn = pyodbc.connect(conn_str, autocommit=True)
    try:
        cursor = conn.cursor()
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
