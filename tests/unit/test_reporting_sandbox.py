"""Unit tests for the Reporting live-SQL sandbox (security boundary)."""

import re

import pytest

from nx_lib.reporting.sandbox import (
    SqlSandboxError,
    fetch_capped,
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


# ---- Task 30 (D-CTE): WITH-rooted queries can't be wrapped as a derived table --
# `SELECT TOP (n) * FROM ( WITH ... ) AS _q` is invalid T-SQL — WITH cannot appear
# inside a derived-table subquery. wrap_with_cap() must pass CTE queries through
# unwrapped; the executor caps them fetch-side instead via fetch_capped().


def test_wrap_with_cap_passes_with_query_through_unwrapped():
    sql = "WITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 100)
    assert out == sql
    assert "FROM ( WITH" not in out
    assert re.search(r"FROM\s*\(\s*WITH", out, re.IGNORECASE) is None


def test_wrap_with_cap_plain_select_still_gets_top_wrap():
    # (b) plain SELECTs are unaffected — same shape as before this fix.
    out = wrap_with_cap("SELECT 1", 25)
    assert out.startswith("SELECT TOP (25) * FROM (")
    assert out.rstrip().endswith(") AS _q")
    assert "SELECT 1" in out


def test_wrap_with_cap_detects_with_after_line_comment():
    sql = "-- note\nWITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 10)
    assert out == sql


def test_wrap_with_cap_detects_with_after_block_comment():
    sql = "/* note */\nWITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 10)
    assert out == sql


def test_wrap_with_cap_detects_with_after_mixed_comments():
    sql = "/* a */ -- b\n  WITH q AS (SELECT 1 AS a) SELECT * FROM q"
    out = wrap_with_cap(sql, 10)
    assert out == sql


def test_wrap_with_cap_detects_with_after_leading_semicolon():
    # `;WITH ...` is idiomatic T-SQL style (WITH must start a batch or
    # follow a semicolon-terminated statement) — sqlglot parses it as a
    # single valid Select, so it reaches wrap_with_cap() with the `;`
    # still attached. Must be passed through unwrapped, same as bare WITH.
    sql = ";WITH q AS (SELECT 1 AS a) SELECT * FROM q"
    assert validate_select(sql) == sql
    out = wrap_with_cap(sql, 10)
    assert out == sql
    assert re.search(r"FROM\s*\(\s*;?\s*WITH", out, re.IGNORECASE) is None


class _FakeCursor:
    """Duck-typed pyodbc-style cursor for exercising fetch_capped() DB-free."""

    def __init__(self, rows):
        self._rows = list(rows)

    def fetchmany(self, n):
        batch, self._rows = self._rows[:n], self._rows[n:]
        return batch


def test_fetch_capped_flags_truncation_for_unwrapped_with_query():
    # (c) Executor-level: a WITH query has no SQL-side TOP cap once wrap_with_cap
    # passes it through unwrapped, so fetch_capped() is the only enforcement —
    # it must still return at most `cap` rows and flag the truncation.
    sql = "WITH q AS (SELECT n FROM t) SELECT n FROM q"
    assert wrap_with_cap(sql, 5) == sql
    cur = _FakeCursor([(i,) for i in range(12)])
    rows, truncated = fetch_capped(cur, 5)
    assert len(rows) == 5
    assert truncated is True


def test_fetch_capped_no_truncation_when_under_cap():
    cur = _FakeCursor([(1,), (2,)])
    rows, truncated = fetch_capped(cur, 5)
    assert rows == [[1], [2]]
    assert truncated is False


def test_fetch_capped_exact_cap_count_is_not_flagged_truncated():
    # The precise +1-row probe must NOT false-positive when the real result
    # set is exactly `cap` rows (no more) — unlike the old len(rows) >= cap
    # heuristic this replaces.
    cur = _FakeCursor([(1,), (2,), (3,)])
    rows, truncated = fetch_capped(cur, 3)
    assert len(rows) == 3
    assert truncated is False


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
