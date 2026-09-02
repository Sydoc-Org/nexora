"""Apply pending SQL migrations to a target environment.

The on-disk source of truth for schema changes is ``sql/_migrations/<Db>/*.sql``.
Each migration is applied at most once per database; the runner records what
it has applied in ``dbo.SchemaMigrations`` (created by the bootstrap migration
``0001_init_schema_migrations.sql``).

Usage:
    python scripts/db-migrate.py --env INT                    # apply pending to all tracked DBs
    python scripts/db-migrate.py --env INT --db NexoraDB      # one DB
    python scripts/db-migrate.py --env STAGING                # bring STAGING up to date (no prompt)
    python scripts/db-migrate.py --env PROD --dry-run         # preview
    python scripts/db-migrate.py --env PROD                   # apply (one confirm prompt)
    python scripts/db-migrate.py --env INT --check            # exit 1 if pending (pre-commit)
    python scripts/db-migrate.py --env INT --mark-applied     # record as applied without running

Authoring a migration:
    1. Create ``sql/_migrations/<Db>/<NNNN>_<short_description>.sql`` with the DDL.
    2. Apply to INT:
         - via runner:   ``python scripts/db-migrate.py --env INT``
         - or in SSMS, then mark: ``python scripts/db-migrate.py --env INT --mark-applied``
    3. Commit. Pre-commit hook re-syncs per-object DDL and verifies all
       migrations are applied to INT.
    4. Deploy to PROD: ``git pull && python scripts/db-migrate.py --env PROD``.

Migrations are immutable once applied: the runner refuses to re-run a file
whose checksum no longer matches what was recorded at apply time. To make
further changes, write a new migration.

If a checksum drifts without a real content edit -- e.g. line-ending
renormalization (the checksum is over raw bytes, so CRLF vs LF differs) --
re-bless the recorded checksums to the current file bytes with ``--rebless``
(no SQL is run; pair with ``--dry-run`` to preview first).

Escape hatch (offline): ``SQL_SYNC_SKIP=1`` makes ``--check`` exit 0 without
contacting the DB. Same env var also disables the pre-commit check.
"""

import argparse
import functools
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_ROOT = REPO_ROOT / "sql" / "_migrations"

# (config attribute on nx_lib.config) -> (folder under sql/_migrations/)
TRACKED_DATABASES = [
    ("DB_NEXORA", "NexoraDB"),
    ("DB_GENERALI", "GeneraliDB"),
]


def load_nexora_config(env_name: str):
    """Load nx_lib/config.py directly (skipping the package __init__) so we get
    the same env loading and DB-name resolution as the running Flask app.
    Mirrors the pattern in sql/sync-from-db.py."""
    os.environ["ENVIRONMENT"] = env_name
    spec = importlib.util.spec_from_file_location(
        "_nexora_config_for_migrate",
        str(REPO_ROOT / "nx_lib" / "config.py"),
    )
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return cfg


_SQLCMD_FALLBACK_DIRS = (
    r"C:\Program Files\SqlCmd",
    r"C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn",
    r"C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\180\Tools\Binn",
    r"C:\Program Files (x86)\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn",
    r"C:\Program Files (x86)\Microsoft SQL Server\Client SDK\ODBC\180\Tools\Binn",
)


def find_sqlcmd() -> str:
    """Locate sqlcmd, with a fallback for hosts where the System PATH set after
    a service started doesn't yet reflect the install dir (GitHub Actions
    self-hosted runner pattern — see 2026-05-28 deploy postmortem)."""
    exe = shutil.which("sqlcmd") or shutil.which("sqlcmd.exe")
    if exe:
        return exe
    for d in _SQLCMD_FALLBACK_DIRS:
        candidate = Path(d) / "sqlcmd.exe"
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(
        "sqlcmd not found on PATH or in common install dirs. Install SQL "
        "Server Command Line Utilities (ships with SSMS / mssql-tools). "
        f"Searched fallbacks: {', '.join(_SQLCMD_FALLBACK_DIRS)}"
    )


def connect(server: str, db: str, uid: str, pwd: str):
    import pyodbc

    return pyodbc.connect(
        f"DRIVER={{SQL Server}};"
        f"SERVER={server},1433;"
        f"DATABASE={db};"
        f"UID={uid};"
        f"PWD={pwd};"
    )


def applied_filenames(conn) -> dict[str, bytes]:
    """Return {FileName: Checksum} of already-applied migrations.
    Empty dict if dbo.SchemaMigrations doesn't exist (pre-bootstrap)."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT CASE WHEN OBJECT_ID('dbo.SchemaMigrations', 'U') IS NULL " "THEN 1 ELSE 0 END"
        )
        if cur.fetchone()[0] == 1:
            return {}
        cur.execute("SELECT FileName, Checksum FROM dbo.SchemaMigrations")
        return {row[0]: bytes(row[1]) for row in cur.fetchall()}
    finally:
        cur.close()


def list_migration_files(db_folder: str) -> list[Path]:
    folder = MIGRATIONS_ROOT / db_folder
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".sql")


def file_checksum(p: Path) -> bytes:
    return hashlib.sha256(p.read_bytes()).digest()


@functools.lru_cache(maxsize=8)
def _sqlcmd_uses_f(exe: str) -> bool:
    """Whether this sqlcmd build accepts the classic ``-f <codepage>`` flag.

    Classic ODBC sqlcmd needs ``-f 65001`` to read the UTF-8 migration files;
    without it non-ASCII text is read in the host OEM/ANSI codepage and corrupted
    on INSERT (this is how ``0011`` got a mojibake label). go-sqlcmd (the Go
    rewrite, installed at ``C:\\Program Files\\SqlCmd``) does NOT support ``-f``
    (it errors "'f': Unknown Option") and reads input as UTF-8 by default, so the
    flag must be omitted there.

    Probe ``--version``: classic sqlcmd does not understand it and prints
    "Sqlcmd: Error: ...", go-sqlcmd prints its version. Default to classic (keep
    ``-f``) on any uncertainty -- omitting it wrongly silently corrupts non-ASCII
    text, whereas keeping it wrongly fails loudly.
    """
    try:
        r = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=10, check=False
        )
        return "error" in (r.stdout + r.stderr).lower()
    except Exception:
        return True


def _sqlcmd_args(sqlcmd_exe: str, server: str, db: str, uid: str, pwd: str, mig: Path) -> list[str]:
    """Build the sqlcmd argv for one migration file.

    ``-f 65001`` (classic sqlcmd only -- see _sqlcmd_uses_f) forces the UTF-8
    codepage so non-ASCII migration text is not corrupted on INSERT. go-sqlcmd
    reads UTF-8 by default and rejects ``-f``, so it is omitted there. apply_one
    decodes the captured output as UTF-8 to match.
    """
    args = [
        sqlcmd_exe,
        "-S",
        f"{server},1433",
        "-d",
        db,
        "-U",
        uid,
        "-P",
        pwd,
        "-i",
        str(mig),
    ]
    if _sqlcmd_uses_f(sqlcmd_exe):
        args += ["-f", "65001"]  # UTF-8 in/out so non-ASCII migration text is not corrupted
    args += [
        "-b",  # exit non-zero on SQL errors
        "-X",
        "1",  # disable interactive commands (ED, !!, etc.)
        "-r",
        "1",  # all error messages -> stderr
    ]
    return args


def apply_one(sqlcmd_exe: str, server: str, db: str, uid: str, pwd: str, mig: Path) -> None:
    """Run a migration through sqlcmd. Raises on non-zero exit."""
    cmd = _sqlcmd_args(sqlcmd_exe, server, db, uid, pwd, mig)
    res = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if res.stdout:
        sys.stdout.write(res.stdout)
    if res.returncode != 0:
        if res.stderr:
            sys.stderr.write(res.stderr)
        raise RuntimeError(f"{mig.name} failed (sqlcmd exit {res.returncode})")


def record_applied(conn, filename: str, checksum: bytes) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO dbo.SchemaMigrations (FileName, Checksum) VALUES (?, ?)",
            filename,
            checksum,
        )
        conn.commit()
    finally:
        cur.close()


def rebless_checksum(conn, filename: str, checksum: bytes) -> None:
    """Overwrite the recorded checksum of an already-applied migration."""
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE dbo.SchemaMigrations SET Checksum = ? WHERE FileName = ?",
            checksum,
            filename,
        )
        conn.commit()
    finally:
        cur.close()


def plan_for_db(conn, db_folder: str) -> tuple[list[Path], list[Path]]:
    """Return (to_apply, mutated).
    - to_apply: unapplied files, in name order.
    - mutated: applied files whose on-disk checksum no longer matches what was
      recorded (the file was edited post-apply -- always a mistake)."""
    applied = applied_filenames(conn)
    to_apply: list[Path] = []
    mutated: list[Path] = []
    for f in list_migration_files(db_folder):
        if f.name not in applied:
            to_apply.append(f)
        elif file_checksum(f) != applied[f.name]:
            mutated.append(f)
    return to_apply, mutated


def run_for_db(args, cfg, db_folder: str, db_name: str, sqlcmd_exe: str) -> tuple[int, int]:
    """Process pending migrations for one DB. Returns (applied_count, pending_before)."""
    print(f"[{db_folder}] db={db_name} env={args.env}")
    conn = connect(cfg.DB_SERVER_PRD, db_name, cfg.DB_UID, cfg.DB_PWD)
    try:
        to_apply, mutated = plan_for_db(conn, db_folder)

        if args.rebless:
            if not mutated:
                print("  no checksum drift -- nothing to re-bless")
                return (0, 0)
            print(f"  {len(mutated)} migration(s) with drifted checksums:")
            for m in mutated:
                print(f"    ~ {m.name}")
            if args.dry_run:
                print("  (--dry-run, not re-blessed)")
                return (0, len(mutated))
            if args.env == "PROD" and not args.yes:
                ans = (
                    input(f"  re-bless {len(mutated)} checksum(s) on PROD/{db_name}? [y/N] ")
                    .strip()
                    .lower()
                )
                if ans != "y":
                    print("  skipped")
                    return (0, len(mutated))
            for m in mutated:
                rebless_checksum(conn, m.name, file_checksum(m))
                print(f"  ~> {m.name} (checksum updated)")
            return (0, 0)

        if mutated:
            sys.stderr.write(f"  ERROR: {len(mutated)} migration(s) edited after being applied:\n")
            for m in mutated:
                sys.stderr.write(f"    {m.name}\n")
            sys.stderr.write(
                "  Migrations are immutable. Add a new migration to make further changes.\n"
            )
            raise SystemExit(3)

        if not to_apply:
            print("  up-to-date")
            return (0, 0)

        verb = "mark applied" if args.mark_applied else "apply"
        print(f"  {len(to_apply)} pending ({verb}):")
        for f in to_apply:
            print(f"    + {f.name}")

        if args.check:
            return (0, len(to_apply))
        if args.dry_run:
            print("  (--dry-run, not applied)")
            return (0, len(to_apply))

        if args.env == "PROD" and not args.yes and not args.mark_applied:
            ans = (
                input(f"  apply {len(to_apply)} migration(s) to PROD/{db_name}? [y/N] ")
                .strip()
                .lower()
            )
            if ans != "y":
                print("  skipped")
                return (0, len(to_apply))

        # mark-applied still needs the bootstrap migration to actually run, because
        # without dbo.SchemaMigrations we can't record anything.
        for f in to_apply:
            checksum = file_checksum(f)
            if args.mark_applied and applied_filenames(conn):
                # Table exists -- just record without running.
                print(f"  -  {f.name} (recorded, not run)")
            else:
                print(f"  -> {f.name}")
                try:
                    apply_one(sqlcmd_exe, cfg.DB_SERVER_PRD, db_name, cfg.DB_UID, cfg.DB_PWD, f)
                except RuntimeError:
                    sys.stderr.write(
                        f"\nHINT: if {f.name} was already applied manually (e.g. in SSMS), "
                        f"record it without re-running:\n"
                        f"  python scripts/db-migrate.py --env {args.env} --db {db_folder} --mark-applied\n\n"
                    )
                    raise
            record_applied(conn, f.name, checksum)

        return (len(to_apply), 0)
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    p.add_argument(
        "--env",
        default="INT",
        choices=("INT", "STAGING", "PROD"),
        help="Which .env file to load (default: INT)",
    )
    p.add_argument("--db", default=None, help="Limit to one DB folder (NexoraDB|GeneraliDB)")
    p.add_argument("--dry-run", action="store_true", help="Show pending migrations, don't run them")
    p.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if any pending migrations (for pre-commit hook)",
    )
    p.add_argument(
        "--mark-applied",
        action="store_true",
        help="Record files as applied without running them (when already run in SSMS)",
    )
    p.add_argument(
        "--rebless",
        action="store_true",
        help="Update recorded checksums of already-applied migrations whose file "
        "bytes drifted (e.g. line-ending renormalization). Runs no SQL; "
        "use with --dry-run to preview.",
    )
    p.add_argument("--yes", "-y", action="store_true", help="Skip the PROD confirmation prompt")
    args = p.parse_args()

    if os.environ.get("SQL_SYNC_SKIP") == "1":
        print("[migrate] SQL_SYNC_SKIP=1 -- skipping")
        return 0

    cfg = load_nexora_config(args.env)
    if not (cfg.DB_SERVER_PRD and cfg.DB_UID and cfg.DB_PWD):
        sys.stderr.write("Missing DB_SERVER_PRD / DB_UID / DB_PWD in env\n")
        return 2

    targets = [
        (attr, folder) for attr, folder in TRACKED_DATABASES if not args.db or folder == args.db
    ]
    if not targets:
        sys.stderr.write(f"Unknown --db value: {args.db}\n")
        return 2

    # sqlcmd only needed when we'll actually execute SQL.
    sqlcmd_exe = ""
    if not (args.check or args.dry_run or args.mark_applied or args.rebless):
        sqlcmd_exe = find_sqlcmd()

    total_applied = 0
    total_pending = 0
    for cfg_attr, folder in targets:
        db_name = getattr(cfg, cfg_attr, None)
        if not db_name:
            sys.stderr.write(f"nx_lib.config has no value for {cfg_attr}\n")
            return 2
        applied, pending = run_for_db(args, cfg, folder, db_name, sqlcmd_exe)
        total_applied += applied
        total_pending += pending

    if args.check:
        if total_pending:
            sys.stderr.write(
                f"\n[migrate] {total_pending} unapplied migration(s) on {args.env}.\n"
                "Run: python scripts/db-migrate.py --env INT\n"
                "Or (if already applied in SSMS): python scripts/db-migrate.py --env INT --mark-applied\n"
                "Bypass: SQL_SYNC_SKIP=1 git commit ... or git commit --no-verify\n"
            )
            return 1
        print("[migrate] all migrations applied.")
        return 0

    print(f"[migrate] done. applied={total_applied}, env={args.env}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
