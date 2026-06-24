"""Unit tests for the Reporting live-SQL sandbox (security boundary)."""

import pytest

from nx_lib.reporting.sandbox import (
    SqlSandboxError,
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
