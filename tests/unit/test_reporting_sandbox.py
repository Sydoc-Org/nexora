"""Unit tests for the Reporting live-SQL sandbox (security boundary)."""

import pytest

from nx_lib.reporting.sandbox import (
    SqlSandboxError,
    humanize_sql_error,
    validate_select,
    wrap_with_cap,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select Id, Name from dbo.SomeView where Name = 'x'",
        "WITH c AS (SELECT 1 AS n) SELECT n FROM c",
        "SELECT a FROM t1 UNION SELECT a FROM t2",
        "SELECT /* note */ 1 -- trailing comment",
        "SELECT sp_balance, sp_name FROM Salespersons",
        "SELECT 1 AS intolerance",
        "SELECT /* DROP TABLE x */ 1",
    ],
)
def test_accepts_read_only_selects(sql):
    assert validate_select(sql) == sql.strip()


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "TRUNCATE TABLE t",
        "ALTER TABLE t ADD c INT",
        "CREATE TABLE t (a INT)",
        "MERGE t USING s ON t.id = s.id WHEN MATCHED THEN DELETE",
        "EXEC sp_who",
        "SELECT * FROM t; DROP TABLE t",
        "SELECT 1) AS _q; DROP TABLE t --",
        "SELECT * INTO newt FROM t",
        "GRANT SELECT ON t TO public",
        "SELECT * FROM OPENROWSET('x','y','z')",
        "",
        "   ",
    ],
)
def test_rejects_non_read_only(sql):
    with pytest.raises(SqlSandboxError):
        validate_select(sql)


def test_too_long_rejected():
    with pytest.raises(SqlSandboxError) as ei:
        validate_select("SELECT " + ("1," * 12000) + "1")
    assert ei.value.rule == "too_long"


def test_error_carries_rule():
    with pytest.raises(SqlSandboxError) as ei:
        validate_select("DROP TABLE t")
    assert ei.value.rule in ("blocked_keyword", "forbidden_node", "not_select")


def test_wrap_with_cap_shape():
    out = wrap_with_cap("SELECT 1", 50000)
    assert out.startswith("SELECT TOP (50000) * FROM (")
    assert out.rstrip().endswith(") AS _q")


def test_wrap_with_cap_coerces_int():
    assert "TOP (10)" in wrap_with_cap("SELECT 1", "10")


def test_sandbox_error_token_carries_dynamic_part():
    # The view boundary translates rule-keyed messages; the dynamic bit
    # (keyword/construct name) must ride on the exception, not be regexed
    # back out of the English message.
    with pytest.raises(SqlSandboxError) as ei:
        validate_select("SELECT 1; DROP TABLE x")
    assert ei.value.rule == "blocked_keyword"
    assert ei.value.token.upper() == "DROP"


# ---- Task 6: humanize_sql_error (pyodbc/ODBC driver noise -> teaching text) --

# The exact live-audit pyodbc str(exception) text for a derived-table ORDER BY
# without TOP/OFFSET (SQL Server error 1033) — known and hinted in v1.
_ODBC_ORDER_BY_1033 = (
    "('42000', '[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
    "The ORDER BY clause is invalid in views, inline functions, derived "
    "tables, subqueries, and common table expressions, unless TOP, OFFSET "
    "or FOR XML is also specified. (1033) (SQLExecDirectW)')"
)

# An incorrect-syntax message (error 102) — cleaned like any ODBC error, but
# unmapped in v1 so no Hint: line is appended.
_ODBC_INCORRECT_SYNTAX_102 = (
    "('42000', \"[42000] [Microsoft][ODBC SQL Server Driver][SQL Server]"
    "Incorrect syntax near 'FROM'. (102) (SQLExecDirectW)\")"
)


def test_humanize_sql_error_strips_noise_and_hints_known_code():
    out = humanize_sql_error(_ODBC_ORDER_BY_1033)
    assert "ORDER BY clause is invalid" in out
    assert "Hint:" in out
    assert "SQLExecDirectW" not in out
    assert "[Microsoft]" not in out


def test_humanize_sql_error_strips_noise_without_hint_for_unmapped_code():
    out = humanize_sql_error(_ODBC_INCORRECT_SYNTAX_102)
    assert "Incorrect syntax near 'FROM'" in out
    assert "Hint:" not in out
    assert "SQLExecDirectW" not in out
    assert "[Microsoft]" not in out


def test_humanize_sql_error_passes_through_non_odbc_message():
    msg = "unknown metric: 'x'"
    assert humanize_sql_error(msg) == msg
