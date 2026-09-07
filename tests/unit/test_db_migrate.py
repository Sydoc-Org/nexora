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


def test_sqlcmd_args_emit_db_name_variables():
    # A migration that reaches across databases (#254: a NexoraDB view over the
    # Octo statistics tables) cannot hardcode the target name — it differs per
    # environment. It writes [$(StatisticsDb)] and sqlcmd substitutes.
    mod = _load_db_migrate()
    with mock.patch.object(mod, "_sqlcmd_uses_f", return_value=False):
        args = mod._sqlcmd_args(
            "sqlcmd.exe",
            "SRV",
            "MyDb",
            "uid",
            "pwd",
            Path("0097_x.sql"),
            {"StatisticsDb": "sydoc_stat_INT"},
        )
    assert "-v" in args
    assert "StatisticsDb=sydoc_stat_INT" in args


def test_sqlcmd_args_without_variables_are_unchanged():
    # Passing no variables must not add a bare -v (sqlcmd would reject it).
    mod = _load_db_migrate()
    with mock.patch.object(mod, "_sqlcmd_uses_f", return_value=False):
        args = mod._sqlcmd_args("sqlcmd.exe", "SRV", "MyDb", "uid", "pwd", Path("0011_x.sql"))
    assert "-v" not in args


def test_sqlcmd_vars_skips_unset_databases():
    # An environment without a Generali DB must not get GeneraliDb="" — sqlcmd
    # would substitute an empty name and fail with a confusing parse error.
    mod = _load_db_migrate()

    class Cfg:
        DB_NEXORA = "NexoraDB_INT"
        DB_STATISTICS = "sydoc_stat_INT"
        DB_GENERALI = None

    variables = mod.sqlcmd_vars(Cfg())
    assert variables["StatisticsDb"] == "sydoc_stat_INT"
    assert variables["NexoraDb"] == "NexoraDB_INT"
    assert "GeneraliDb" not in variables
    assert "OctoDb" not in variables
