r"""Structural guards for ops/cleanup/csvLogs_toDB.ps1.

The script drains var/logs/user/<hour>/nexora_logs.csv into dbo.Logs and then
deletes the folder. It cannot be exercised from pytest -- it needs PowerShell,
Windows auth and a live SQL Server -- but the properties that matter are
structural, and the bug it used to have was structural too: `Remove-Item` sat
after the insert loop with no error handling, so a failed or partial import
still deleted the hour it had just failed to save, and nothing was logged, so
it was undetectable.

These pin the shape. The behaviour was verified by hand against a scratch table
on INTSQL01: a CSV whose second row overflows Path nvarchar(100) rolls back,
keeps its folder, still lets the next folder import, and exits 1.
"""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "cleanup" / "csvLogs_toDB.ps1"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _code_line_numbers(needle: str):
    """Zero-based indices of code lines containing `needle`.

    Past the `<# ... #>` header and skipping `#` comments: the header quotes
    `Remove-Item` while describing the bug this script used to have, so
    scanning the raw file finds prose rather than code.
    """
    lines = _src().splitlines()
    start = next((i + 1 for i, ln in enumerate(lines) if ln.strip() == "#>"), 0)
    return [
        i
        for i, ln in enumerate(lines)
        if i >= start and not ln.strip().startswith("#") and needle in ln
    ]


def test_script_exists():
    assert SCRIPT.is_file(), f"{SCRIPT} is missing"


def test_errors_are_terminating():
    """Without this a failed ExecuteNonQuery is non-terminating, the catch never
    fires, and the delete runs anyway -- the original bug."""
    assert "$ErrorActionPreference = 'Stop'" in _src()


def test_each_folder_is_a_transaction():
    src = _src()
    assert "BeginTransaction()" in src
    assert ".Commit()" in src
    assert ".Rollback()" in src


def test_the_delete_only_follows_a_commit():
    """The whole point: no Remove-Item may run on a folder whose rows were not
    committed."""
    removes = _code_line_numbers("Remove-Item")
    assert removes, "no Remove-Item at all -- folders would accumulate forever"
    lines = _src().splitlines()
    for i in removes:
        window = "\n".join(lines[max(0, i - 6) : i])
        assert ".Commit()" in window or "no csv" in window.lower(), (
            f"Remove-Item on line {i + 1} is not guarded by a Commit; a failed "
            "import would delete the hour it could not save"
        )
    assert len(removes) == 2, (
        "expected exactly 2 Remove-Item calls (the committed folder, and the "
        f"no-csv branch), found {len(removes)}"
    )


def test_one_connection_for_the_whole_run():
    """It used to open one per row -- roughly 8k connect/disconnect cycles a day
    against PRDSQL01."""
    assert len(_code_line_numbers("New-Object System.Data.SqlClient.SqlConnection")) == 1


def test_the_live_hour_is_left_alone():
    """Importing and deleting the folder the app is still appending to races the
    web process: a request logged between the read and the delete is gone."""
    src = _src()
    assert "yyyyMMddHH" in src
    assert "-ne $currentHour" in src


def test_it_reports_and_signals_failure():
    """Silent success and silent failure used to look identical."""
    src = _src()
    assert "Write-Output" in src
    assert "exit 1" in src, "a kept-back folder must fail the scheduled task"


def test_semantics_of_anonymous_rows_are_preserved():
    """dbo.Logs holds 856,638 rows, 155,015 of them anonymous as UserID = 0 and
    Username = '' -- not one NULL. AddWithValue sends Import-Csv's '' as a
    string and SQL Server converts it, which is what produces that. Typed
    Int/Float parameters would send DBNull and split the table into two
    conventions mid-history."""
    src = _src()
    assert "AddWithValue" in src
    assert "SqlDbType" not in src, (
        "typed parameters would write NULL where every existing anonymous row "
        "has 0 / '' -- see the comment in the script"
    )
