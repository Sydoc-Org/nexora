"""Unit tests for scripts/db-migrate.py command construction.

The script is hyphenated (not importable as a package), so it is loaded from its
path. These tests cover only the pure sqlcmd-argument builder — no DB or sqlcmd
is invoked (the classic-vs-go-sqlcmd `--version` probe is stubbed).
"""

import importlib.util
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_db_migrate():
    spec = importlib.util.spec_from_file_location(
        "db_migrate_under_test", REPO_ROOT / "scripts" / "db-migrate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sqlcmd_args_set_utf8_input_codepage_classic():
    # Classic ODBC sqlcmd: migration files are UTF-8. Without -f 65001 sqlcmd reads
    # them as the host's OEM/ANSI codepage and corrupts any non-ASCII (em-dash,
    # umlauts) on INSERT — which is how migration 0011 stored a mojibake label.
    mod = _load_db_migrate()
    with mock.patch.object(mod, "_sqlcmd_uses_f", return_value=True):
        args = mod._sqlcmd_args(
            "sqlcmd.exe", "SRV", "MyDb", "uid", "pwd", Path("sql/_migrations/NexoraDB/0011_x.sql")
        )
    assert "-f" in args
    assert args[args.index("-f") + 1] == "65001"


def test_sqlcmd_args_omits_f_for_go_sqlcmd():
    # go-sqlcmd rejects -f ("'f': Unknown Option") and reads UTF-8 by default, so
    # the flag must be omitted there (the runner uses go-sqlcmd).
    mod = _load_db_migrate()
    with mock.patch.object(mod, "_sqlcmd_uses_f", return_value=False):
        args = mod._sqlcmd_args("sqlcmd.exe", "SRV", "MyDb", "uid", "pwd", Path("0011_x.sql"))
    assert "-f" not in args


def test_sqlcmd_args_keep_existing_safety_flags():
    mod = _load_db_migrate()
    with mock.patch.object(mod, "_sqlcmd_uses_f", return_value=True):
        args = mod._sqlcmd_args("sqlcmd.exe", "SRV", "MyDb", "uid", "pwd", Path("0011_x.sql"))
    assert args[0] == "sqlcmd.exe"
    assert "-b" in args  # abort on SQL error
    assert "-i" in args  # input file
    assert "-S" in args and "SRV,1433" in args
    assert "-d" in args and "MyDb" in args


def test_sqlcmd_uses_f_distinguishes_classic_from_go():
    # `--version` probe: classic sqlcmd does not understand it and prints
    # "Sqlcmd: Error: ..." (-> keep -f); go-sqlcmd prints a version (-> omit -f).
    mod = _load_db_migrate()
    with mock.patch.object(
        mod.subprocess,
        "run",
        return_value=mock.Mock(stdout="Sqlcmd: Error: '-' ...", stderr="", returncode=0),
    ):
        assert mod._sqlcmd_uses_f("classic.exe") is True
    with mock.patch.object(
        mod.subprocess,
        "run",
        return_value=mock.Mock(stdout="sqlcmd version 1.8.0\n", stderr="", returncode=0),
    ):
        assert mod._sqlcmd_uses_f("go-sqlcmd.exe") is False
