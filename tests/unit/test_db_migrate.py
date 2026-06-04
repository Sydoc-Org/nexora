"""Unit tests for scripts/db-migrate.py command construction.

The script is hyphenated (not importable as a package), so it is loaded from its
path. These tests cover only the pure sqlcmd-argument builder — no DB/sqlcmd is
invoked.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_db_migrate():
    spec = importlib.util.spec_from_file_location(
        "db_migrate_under_test", REPO_ROOT / "scripts" / "db-migrate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sqlcmd_args_set_utf8_input_codepage():
    # Migration files are UTF-8. Without -f 65001 sqlcmd reads them as the host's
    # OEM/ANSI codepage and corrupts any non-ASCII (em-dash, umlauts) on INSERT —
    # which is exactly how migration 0011 stored a mojibake source label.
    mod = _load_db_migrate()
    args = mod._sqlcmd_args(
        "sqlcmd.exe", "SRV", "MyDb", "uid", "pwd", Path("sql/_migrations/NexoraDB/0011_x.sql")
    )
    assert "-f" in args
    assert args[args.index("-f") + 1] == "65001"


def test_sqlcmd_args_keep_existing_safety_flags():
    mod = _load_db_migrate()
    args = mod._sqlcmd_args("sqlcmd.exe", "SRV", "MyDb", "uid", "pwd", Path("0011_x.sql"))
    assert args[0] == "sqlcmd.exe"
    assert "-b" in args  # abort on SQL error
    assert "-i" in args  # input file
    assert "-S" in args and "SRV,1433" in args
    assert "-d" in args and "MyDb" in args
