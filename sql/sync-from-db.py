"""Regenerate sql/<Database>/ folders from the live INT databases.

The database is the source of truth. This script dumps the current DDL of
every tracked database into sql/<Database>/ using mssql-scripter, then
reorganizes the flat output into an SSMS Object Explorer-style folder tree:

    sql/NexoraDB/
        Tables/
        Views/
        Programmability/
            StoredProcedures/
            Functions/
            Triggers/
            Types/
        Security/Schemas/

Hand-written migration scripts live separately under sql/_migrations/<Db>/;
this script never touches those. To apply or verify migrations, use
scripts/db-migrate.py.

Usage:
    python sql/sync-from-db.py                  # sync all tracked DBs from INT
    python sql/sync-from-db.py --db NexoraDB    # only one DB
    python sql/sync-from-db.py --env PROD       # rare: pull from PROD instead
    python sql/sync-from-db.py --check          # pre-commit mode (exit 1 on drift)

Escape hatch: set SQL_SYNC_SKIP=1 to make --check exit 0 without running
(useful when offline or temporarily without DB access).
"""

import argparse
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_ROOT = REPO_ROOT / "sql"

# Which nx_lib.config attribute holds each DB name  ->  on-disk folder under sql/
# Resolved via nx_lib/config.py so defaults (e.g. DB_GENERALI -> "Generali") match the app.
TRACKED_DATABASES = [
    ("DB_NEXORA",   "NexoraDB"),
    ("DB_GENERALI", "GeneraliDB"),
]

# mssql-scripter encodes type in the filename:  schema.object.<Type>.sql
# This maps that <Type> token to the SSMS-mirroring destination folder.
TYPE_TO_FOLDER = {
    "Table":                "Tables",
    "View":                 "Views",
    "StoredProcedure":      "Programmability/StoredProcedures",
    "UserDefinedFunction":  "Programmability/Functions",
    "Trigger":              "Programmability/Triggers",
    "UserDefinedTableType": "Programmability/Types",
    "UserDefinedDataType":  "Programmability/Types",
    "Schema":               "Security/Schemas",
    "User":                 "Security/Users",
    "Role":                 "Security/Roles",
    # Skip: "Database" (the database itself — no useful DDL for our purposes)
}


def find_scripter() -> str:
    """Locate the mssql-scripter executable. Raises if not installed."""
    exe = shutil.which("mssql-scripter") or shutil.which("mssql-scripter.exe")
    if not exe:
        raise RuntimeError(
            "mssql-scripter not found. Install with:\n"
            "    pip install -r sql/requirements.txt"
        )
    return exe


def parse_scripter_name(filename: str) -> tuple[str, str] | None:
    """Parse a scripter filename '<basename>.<Type>.sql' -> (basename, type).
    Returns None for files that don't match the expected pattern."""
    if not filename.lower().endswith(".sql"):
        return None
    name = filename[:-4]
    if "." not in name:
        return None
    basename, _, kind = name.rpartition(".")
    return (basename, kind) if basename and kind else None


def script_database(exe: str, server: str, db: str, uid: str, pwd: str, out_dir: Path) -> None:
    """Invoke mssql-scripter: one .sql per object, drop+create, no header noise."""
    cmd = [
        exe,
        "-S", f"{server},1433",
        "-d", db,
        "-U", uid,
        "-P", pwd,
        "-f", str(out_dir),
        "--file-per-object",
        "--script-drop-create",
        "--exclude-headers",
        "--target-server-version", "vNext",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stdout + "\n" + res.stderr + "\n")
        raise RuntimeError(f"mssql-scripter failed for {db} (exit {res.returncode})")
    # mssql-scripter sometimes exits 0 on bad args after printing usage. Detect
    # the no-files case explicitly so we don't atomic-swap an empty dir over
    # real content.
    produced = sum(1 for f in out_dir.iterdir() if f.is_file() and f.suffix.lower() == ".sql")
    if produced == 0:
        sys.stderr.write((res.stdout or "") + "\n" + (res.stderr or "") + "\n")
        raise RuntimeError(f"mssql-scripter produced no files for {db}")


def organize(raw_dir: Path, target: Path) -> int:
    """Classify each scripted file by the type token in its filename and
    move it into the matching SSMS folder. Returns count of objects placed."""
    moved = 0
    skipped_types: set[str] = set()
    for fp in sorted(raw_dir.iterdir()):
        if not fp.is_file():
            continue
        parsed = parse_scripter_name(fp.name)
        if parsed is None:
            continue
        basename, kind = parsed
        sub = TYPE_TO_FOLDER.get(kind)
        if sub is None:
            skipped_types.add(kind)
            continue
        dest_dir = target / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(fp), str(dest_dir / f"{basename}.sql"))
        moved += 1
    if skipped_types:
        print(f"  skipped types: {', '.join(sorted(skipped_types))}")
    return moved


def _force_writable(_func, path, _exc):
    """rmtree onexc handler: clear the read-only bit and retry the call.
    OneDrive often marks synced files read-only, which trips shutil.rmtree."""
    try:
        os.chmod(path, stat.S_IWRITE)
        _func(path)
    except Exception:
        pass


def rename_robust(src: Path, dst: Path, attempts: int = 8) -> None:
    """Path.rename with retries for OneDrive transient locks."""
    for i in range(attempts):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.4 * (i + 1))


def rmtree_robust(p: Path, attempts: int = 5, required: bool = True) -> bool:
    """rmtree with read-only clearing and retries for OneDrive-locked dirs.
    Returns True on success. If required=False, swallows the final failure."""
    if not p.exists():
        return True
    for i in range(attempts):
        try:
            # Python 3.12+ uses onexc; older uses onerror. Try onexc first.
            try:
                shutil.rmtree(p, onexc=_force_writable)
            except TypeError:
                shutil.rmtree(p, onerror=lambda f, pth, _: _force_writable(f, pth, None))
            return True
        except PermissionError:
            if i < attempts - 1:
                time.sleep(0.4 * (i + 1))
                continue
            if not required:
                print(f"  warn: could not remove {p.name} (likely OneDrive lock); leaving in place")
                return False
            raise


def sync_one(exe: str, db: str, folder: str, server: str, uid: str, pwd: str) -> None:
    print(f"[{folder}] db={db}")
    target  = SQL_ROOT / folder
    staging = SQL_ROOT / f".{folder}.staging"
    backup  = SQL_ROOT / f".{folder}.bak"

    rmtree_robust(staging)
    rmtree_robust(backup)
    raw = staging / "_raw"
    raw.mkdir(parents=True)

    try:
        script_database(exe, server, db, uid, pwd, raw)
        moved = organize(raw, staging)
        rmtree_robust(raw)
        print(f"  organized {moved} object(s)")

        # atomic swap: target -> backup, staging -> target, drop backup
        if target.exists():
            rename_robust(target, backup)
        rename_robust(staging, target)
        # Dropping the backup is best-effort; the swap is already committed.
        rmtree_robust(backup, required=False)
    except Exception:
        rmtree_robust(staging, required=False)
        if backup.exists() and not target.exists():
            rename_robust(backup, target)
        raise


def load_nexora_config(env_name: str):
    """Load nx_lib/config.py directly (skipping the package __init__) so we
    get the same DB-name resolution as the running Flask app, including its
    defaults (e.g. DB_GENERALI -> 'Generali' when the env var is unset)."""
    os.environ["ENVIRONMENT"] = env_name
    spec = importlib.util.spec_from_file_location(
        "_nexora_config_for_sync",
        str(REPO_ROOT / "nx_lib" / "config.py"),
    )
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return cfg


def git_unstaged_under_sql() -> str:
    """Return only true drift under sql/: worktree differs from index, plus
    any new untracked files the sync produced. Already-staged changes are not
    drift — they're what the user is about to commit."""
    modified = subprocess.run(
        ["git", "diff", "--name-only", "--", "sql/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    ).stdout.strip().splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "sql/"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    ).stdout.strip().splitlines()
    lines = [f" M {p}" for p in modified] + [f"?? {p}" for p in untracked]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env", default="INT", choices=("INT", "PROD"),
                   help="Which .env file to load (default: INT)")
    p.add_argument("--db", default=None,
                   help="Sync only one DB (NexoraDB|GeneraliDB)")
    p.add_argument("--check", action="store_true",
                   help="Pre-commit mode: exit 1 if sql/ drifted after sync")
    args = p.parse_args()

    if args.check and os.environ.get("SQL_SYNC_SKIP") == "1":
        print("[sync] SQL_SYNC_SKIP=1 — skipping")
        return 0

    exe = find_scripter()
    cfg = load_nexora_config(args.env)

    if not (cfg.DB_SERVER_PRD and cfg.DB_UID and cfg.DB_PWD):
        sys.stderr.write("Missing DB_SERVER_PRD / DB_UID / DB_PWD in env\n")
        return 2

    targets = [(attr, folder) for attr, folder in TRACKED_DATABASES
               if not args.db or folder == args.db]
    if not targets:
        sys.stderr.write(f"Unknown --db value: {args.db}\n")
        return 2

    for cfg_attr, folder in targets:
        db = getattr(cfg, cfg_attr, None)
        if not db:
            sys.stderr.write(f"nx_lib.config has no value for {cfg_attr}\n")
            return 2
        sync_one(exe, db, folder, cfg.DB_SERVER_PRD, cfg.DB_UID, cfg.DB_PWD)

    if args.check:
        drift = git_unstaged_under_sql()
        if drift:
            print("\n[sync] sql/ drifted from INT — regenerated files are unstaged.")
            print("Review, `git add sql/`, and re-commit. Skip with SQL_SYNC_SKIP=1 or --no-verify.\n")
            print(drift)
            return 1

    print("[sync] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
