"""Unit tests for the display-only T-SQL pretty-printer (sqlformat).

format_sql() feeds the Show-query panels' sqlPretty field. It must be
best-effort: anything sqlglot can't parse comes back unchanged, because a
formatting failure must never break a run response.
"""

import pytest

from nx_lib.reporting.sqlformat import format_sql, inline_sql_params

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


def test_inline_replaces_placeholders_in_order():
    out = inline_sql_params("SELECT * FROM t WHERE d >= ? AND d < ?", ["2026-07-01", "2026-08-01"])
    assert out == "SELECT * FROM t WHERE d >= '2026-07-01' AND d < '2026-08-01'"


def test_inline_handles_scalar_types():
    out = inline_sql_params(
        "SELECT ? AS s, ? AS n, ? AS f, ? AS b1, ? AS b0, ? AS x",
        ["it's", 42, 1.5, True, False, None],
    )
    assert out == "SELECT 'it''s' AS s, 42 AS n, 1.5 AS f, 1 AS b1, 0 AS b0, NULL AS x"


def test_inline_never_touches_question_marks_in_strings_or_comments():
    sql = "SELECT '?' AS q FROM t WHERE a = ? -- really?\n"
    assert inline_sql_params(sql, ["x"]) == "SELECT '?' AS q FROM t WHERE a = 'x' -- really?\n"


def test_inline_question_mark_inside_param_value_is_not_reinterpreted():
    # The emitted literal is output, never re-scanned for placeholders.
    out = inline_sql_params("SELECT * FROM t WHERE a LIKE ? AND b = ?", ["%why?%", "z"])
    assert out == "SELECT * FROM t WHERE a LIKE '%why?%' AND b = 'z'"


def test_inline_count_mismatch_returns_none():
    # Substituting with the wrong arity would LIE about what executed.
    assert inline_sql_params("SELECT ? AS a", []) is None
    assert inline_sql_params("SELECT 1 AS a", ["extra"]) is None


def test_inline_unknown_type_returns_none():
    assert inline_sql_params("SELECT ? AS a", [object()]) is None


def test_inline_no_params_is_passthrough():
    assert inline_sql_params("SELECT 1", []) == "SELECT 1"


def test_inline_composes_with_format_sql():
    # The api_run pipeline: pretty first (placeholders survive — pinned above),
    # then inline. Four ? in REAL_BUILDER_SQL, two UNION subqueries.
    pretty = format_sql(REAL_BUILDER_SQL)
    out = inline_sql_params(pretty, ["2026-07-01", "2026-08-01", "2026-07-01", "2026-08-01"])
    assert out.count("'2026-07-01'") == 2
    assert "?" not in out
