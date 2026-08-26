"""Pure predicate-shape tests for the sargable doc-field predicate builder
(#98 Task 12). No live DB -- ``_docfield_predicate`` is a pure function of
(alias, column, column_type, op_key, value) -> (sql_fragment, params)."""

from nx_lib.views.workitems import _docfield_predicate


def test_text_type_eq_is_bare_column_seekable():
    sql, params = _docfield_predicate("s", "DocType", "nvarchar", "eq", "Invoice")
    assert sql == "s.DocType = ?"
    assert params == ["Invoice"]


def test_text_type_contains_is_bare_column_like():
    sql, params = _docfield_predicate("s", "DocType", "nvarchar", "contains", "Inv")
    assert sql == "s.DocType LIKE ?"
    assert params == ["%Inv%"]


def test_int_type_eq_binds_native_int():
    sql, params = _docfield_predicate("s", "CrdNo", "int", "eq", "1216")
    assert sql == "s.CrdNo = ?"
    assert params == [1216]


def test_int_type_eq_non_numeric_value_is_unmatchable():
    sql, params = _docfield_predicate("s", "CrdNo", "int", "eq", "not-a-number")
    assert sql == "1=0"
    assert params == []


def test_int_type_neq_non_numeric_value_is_vacuously_true():
    sql, params = _docfield_predicate("s", "CrdNo", "int", "neq", "not-a-number")
    assert sql == "1=1"
    assert params == []


def test_int_type_contains_falls_back_to_cast():
    sql, params = _docfield_predicate("s", "CrdNo", "int", "contains", "12")
    assert sql == "CAST(s.CrdNo AS NVARCHAR(MAX)) COLLATE DATABASE_DEFAULT LIKE ?"
    assert params == ["%12%"]


def test_null_type_falls_back_to_cast():
    sql, params = _docfield_predicate("s", "X", None, "contains", "v")
    assert sql == "CAST(s.X AS NVARCHAR(MAX)) COLLATE DATABASE_DEFAULT LIKE ?"
    assert params == ["%v%"]


def test_unknown_type_falls_back_to_cast():
    sql, params = _docfield_predicate("s", "X", "date", "eq", "2026-01-01")
    assert sql == "CAST(s.X AS NVARCHAR(MAX)) COLLATE DATABASE_DEFAULT = ?"
    assert params == ["2026-01-01"]
