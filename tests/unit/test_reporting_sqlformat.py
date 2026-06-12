"""Unit tests for the display-only T-SQL pretty-printer (sqlformat).

format_sql() feeds the Show-query panels' sqlPretty field. It must be
best-effort: anything sqlglot can't parse comes back unchanged, because a
formatting failure must never break a run response.
"""

import pytest

from nx_lib.reporting.sqlformat import format_sql

# Shape produced by build_table_query: one line, UNION ALL subqueries,
# pyodbc ? placeholders.
REAL_BUILDER_SQL = (
    "SELECT TOP (5000) [doctype] AS [doctype], COUNT(*) AS [cnt] "
    "FROM (SELECT [DocType] AS [doctype] FROM [dbo].[StatA] "
    "WHERE [ExportDate] >= ? AND [ExportDate] < ? "
    "UNION ALL SELECT [DocType] AS [doctype] FROM [dbo].[StatB] "
    "WHERE [ExportDate] >= ? AND [ExportDate] < ?) t "
    "GROUP BY [doctype] ORDER BY [cnt] DESC"
)


def test_single_line_builder_sql_becomes_multiline():
    out = format_sql(REAL_BUILDER_SQL)
    assert out != REAL_BUILDER_SQL
    assert "\n" in out
    lines = [ln.strip() for ln in out.splitlines()]
    assert any(ln.startswith("SELECT") for ln in lines)
    assert any(ln.startswith("GROUP BY") for ln in lines)


def test_placeholders_survive():
    # pyodbc binds positionally — losing or reordering a ? would lie to the user.
    out = format_sql(REAL_BUILDER_SQL)
    assert out.count("?") == REAL_BUILDER_SQL.count("?")


def test_semantic_text_survives():
    # sqlglot re-generates from the AST (e.g. TOP (n) -> TOP n) — that's fine,
    # but tables, the set op, and the aggregate must still be present.
    out = format_sql(REAL_BUILDER_SQL)
    for token in ("UNION ALL", "[dbo].[StatA]", "[dbo].[StatB]", "COUNT(*)"):
        assert token in out


def test_multiple_statements_are_all_kept():
    # Display-only field must never silently drop statements 2..n.
    out = format_sql("SELECT 1 AS a; SELECT 2 AS b")
    assert out.count("SELECT") == 2


@pytest.mark.parametrize("passthrough", ["THIS IS NOT ((( SQL", "", "   "])
def test_unparseable_or_blank_returns_input_unchanged(passthrough):
    assert format_sql(passthrough) == passthrough


def test_none_is_passed_through():
    assert format_sql(None) is None
