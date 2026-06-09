# tests/unit/test_reporting_query.py
"""Unit tests for nx_lib.reporting.query.build_table_query (pure)."""

import pytest

from nx_lib.reporting.query import (
    QueryBuildError,
    _date_base,
    _date_exprs_for,
    _grain_sql,
    build_table_query,
)

# Two processes; 'pages' only mapped in proc A.
PROCESS_CONFIGS = [
    {
        "process": "acme.inv",
        "table": "dbo.StatA",
        "export_col": "ExportDate",
        "import_col": "ImportDate",
        "condition": "",
    },
    {
        "process": "acme.hr",
        "table": "dbo.StatB",
        "export_col": "ExpD",
        "import_col": "ImpD",
        "condition": "AND IsValid = 1",
    },
]
FIELD_COL_MAPS = {
    "acme.inv": {"doctype": "DocType", "status": "Status", "pages": "PageCount"},
    "acme.hr": {"doctype": "DType", "status": "Stat"},
}
CATALOG = {"doctype", "status", "pages", "date"}


def _rd(**over):
    base = {
        "schemaVersion": 1,
        "source": "docprocessing",
        "visualization": "table",
        "title": "t",
        "subtitle": None,
        "columns": [
            {"field": "doctype", "header": "Type", "agg": None},
            {"field": "pages", "header": "Pages", "agg": None},
        ],
        "groupBy": [],
        "filters": [],
        "sort": [{"field": "doctype", "dir": "asc"}],
        "scope": {"clients": [], "processes": ["acme.inv", "acme.hr"]},
        "rowLimit": 100,
        "sql": None,
        "sqlTarget": None,
    }
    base.update(over)
    return base


def test_builds_union_over_processes_with_top_and_order():
    sql, params = build_table_query(_rd(), PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "UNION ALL" in sql
    assert sql.strip().upper().startswith("SELECT TOP (100)")
    assert "ORDER BY" in sql
    # 'pages' missing in acme.hr → projected as NULL there
    assert "NULL AS [pages]" in sql


def test_unknown_column_raises():
    with pytest.raises(QueryBuildError):
        build_table_query(
            _rd(columns=[{"field": "evil", "header": "x", "agg": None}]),
            PROCESS_CONFIGS,
            FIELD_COL_MAPS,
            row_cap=100,
        )


def test_eq_filter_is_parameterized():
    rd = _rd(filters=[{"field": "status", "op": "eq", "value": "Done"}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "= ?" in sql
    assert "Done" in params


def test_in_filter_expands_placeholders():
    rd = _rd(filters=[{"field": "status", "op": "in", "value": ["A", "B"]}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "IN (?, ?)" in sql
    assert params.count("A") + params.count("B") >= 2


def test_filter_field_unmapped_in_process_excludes_that_process():
    # filter on 'pages' which acme.hr lacks → only acme.inv subquery remains
    rd = _rd(filters=[{"field": "pages", "op": "gt", "value": 3}])
    sql, _params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "dbo.StatA" in sql
    assert "dbo.StatB" not in sql


def test_additional_condition_is_appended():
    sql, _params = build_table_query(_rd(), PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "IsValid = 1" in sql


def test_empty_process_scope_raises():
    with pytest.raises(QueryBuildError):
        build_table_query(
            _rd(scope={"clients": [], "processes": []}),
            [],
            FIELD_COL_MAPS,
            row_cap=100,
        )


def test_row_cap_overrides_definition_limit():
    sql, _ = build_table_query(_rd(rowLimit=999), PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=50)
    assert "SELECT TOP (50)" in sql


def test_sort_invalid_direction_raises():
    rd = _rd(sort=[{"field": "doctype", "dir": "asc; DROP TABLE x--"}])
    with pytest.raises(QueryBuildError):
        build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)


def test_sort_field_not_in_projection_raises():
    # 'status' is not among the selected columns (doctype, pages)
    rd = _rd(sort=[{"field": "status", "dir": "asc"}])
    with pytest.raises(QueryBuildError):
        build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)


def test_processname_eq_filter_restricts_to_single_process():
    rd = _rd(filters=[{"field": "processname", "op": "eq", "value": "acme.inv"}])
    sql, _params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "dbo.StatA" in sql
    assert "dbo.StatB" not in sql


def test_processname_in_filter_restricts_to_listed_processes():
    rd = _rd(filters=[{"field": "processname", "op": "in", "value": ["acme.hr"]}])
    sql, _params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "dbo.StatB" in sql
    assert "dbo.StatA" not in sql


def test_processname_filter_emits_no_where_clause():
    rd = _rd(filters=[{"field": "processname", "op": "eq", "value": "acme.inv"}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    # processname filter selects subqueries; it must not become a WHERE/param.
    assert "acme.inv" not in params


def test_unsupported_filter_op_raises():
    rd = _rd(filters=[{"field": "status", "op": "regex", "value": "x"}])
    with pytest.raises(QueryBuildError):
        build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)


def test_between_filter_parameterizes_both_bounds_in_order():
    rd = _rd(filters=[{"field": "status", "op": "between", "value": ["A", "Z"]}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "BETWEEN ? AND ?" in sql
    assert params.index("A") < params.index("Z")


def test_contains_filter_wraps_and_escapes():
    rd = _rd(filters=[{"field": "status", "op": "contains", "value": "ab"}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "LIKE ? ESCAPE '\\'" in sql
    assert "%ab%" in params


def test_contains_filter_escapes_metacharacters():
    rd = _rd(filters=[{"field": "status", "op": "contains", "value": "50%_x"}])
    _sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    # % and _ in the value are escaped to literals
    assert "%50\\%\\_x%" in params


def test_is_null_filter_emits_no_param():
    rd = _rd(filters=[{"field": "status", "op": "is_null"}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "IS NULL" in sql
    assert params == []


def test_in_filter_with_none_value_matches_nothing():
    rd = _rd(filters=[{"field": "status", "op": "in", "value": None}])
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "1 = 0" in sql
    assert params == []


def test_docprocessing_aggregate_wraps_union():
    from nx_lib.reporting.query import build_table_query

    rd = _rd(
        columns=[{"field": "doctype"}], filters=[], sort=[{"field": "doc_count", "dir": "desc"}]
    )
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql, params = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert sql.startswith("SELECT TOP (100) [doctype], COUNT(*) AS [doc_count] FROM (")
    assert sql.rstrip().endswith("GROUP BY [doctype] ORDER BY [doc_count] DESC")
    assert "UNION ALL" in sql


def test_docprocessing_aggregate_projects_base_field_into_union():
    from nx_lib.reporting.query import build_table_query

    rd = _rd(columns=[{"field": "doctype"}], filters=[], sort=[])
    resolved = [{"code": "pages_sum", "aggregation": "sum", "base_field": "pages"}]
    sql, _ = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=50, resolved_metrics=resolved
    )
    # 'pages' is only mapped in acme.inv -> projected there, NULL in acme.hr.
    assert "AS [pages]" in sql
    assert "SUM([pages]) AS [pages_sum]" in sql


# --- date dimension: pure helpers (Task 3) -----------------------------------


def test_date_base_cast_vs_convert_passthrough():
    assert _date_base("ImportDate") == "CAST(ImportDate AS date)"
    expr = "CONVERT(date, SomeStr, 104)"  # already a CONVERT -> used as-is
    assert _date_base(expr) == expr


def test_grain_sql_each_grain():
    d = "CAST(ImportDate AS date)"
    assert _grain_sql(d, None) == d
    assert _grain_sql(d, "day") == d
    assert _grain_sql(d, "week") == f"DATEADD(week, DATEDIFF(week, 0, {d}), 0)"
    assert _grain_sql(d, "month") == f"DATEFROMPARTS(YEAR({d}), MONTH({d}), 1)"
    assert (
        _grain_sql(d, "quarter")
        == f"DATEFROMPARTS(YEAR({d}), (DATEPART(quarter, {d}) - 1) * 3 + 1, 1)"
    )
    assert _grain_sql(d, "year") == f"DATEFROMPARTS(YEAR({d}), 1, 1)"


def test_grain_sql_rejects_unknown():
    with pytest.raises(QueryBuildError):
        _grain_sql("x", "fortnight")


def test_date_exprs_for_uses_cfg_columns_and_grain():
    cfg = {"process": "acme.inv", "import_col": "ImportDate", "export_col": "ExpD"}
    out = _date_exprs_for(cfg, {"import_date": "month"})
    assert (
        out["import_date"]
        == "DATEFROMPARTS(YEAR(CAST(ImportDate AS date)), MONTH(CAST(ImportDate AS date)), 1)"
    )
    assert out["export_date"] == "CAST(ExpD AS date)"  # no grain -> raw
    # A cfg missing a column omits that date field entirely.
    assert _date_exprs_for({"process": "p", "import_col": None, "export_col": "E"}, {}) == {
        "export_date": "CAST(E AS date)"
    }


# --- date dimension: build_table_query resolution (Task 4) -------------------


def test_projects_raw_import_date():
    rd = _rd(columns=[{"field": "import_date", "header": "Imported", "agg": None}], sort=[])
    sql, _ = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "CAST(ImportDate AS date) AS [import_date]" in sql  # acme.inv
    assert "CAST(ImpD AS date) AS [import_date]" in sql  # acme.hr


def test_projects_month_grain_import_date():
    rd = _rd(
        columns=[{"field": "import_date", "header": "Month", "agg": None, "grain": "month"}],
        sort=[],
    )
    sql, _ = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert (
        "DATEFROMPARTS(YEAR(CAST(ImportDate AS date)), MONTH(CAST(ImportDate AS date)), 1) "
        "AS [import_date]" in sql
    )


def test_date_filter_uses_raw_even_when_column_grained():
    rd = _rd(
        columns=[{"field": "import_date", "header": "Month", "agg": None, "grain": "month"}],
        filters=[{"field": "import_date", "op": "gte", "value": "2026-01-01"}],
        sort=[],
    )
    sql, params = build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)
    assert "CAST(ImportDate AS date) >= ?" in sql  # raw in WHERE
    assert "DATEFROMPARTS(YEAR(CAST(ImportDate AS date))" in sql  # month in SELECT
    assert "2026-01-01" in params


def test_unknown_date_like_field_still_rejected():
    rd = _rd(columns=[{"field": "nope_date", "header": "x", "agg": None}], sort=[])
    with pytest.raises(QueryBuildError):
        build_table_query(rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100)


def test_aggregate_groups_by_month_grain_dim():
    rd = _rd(
        columns=[{"field": "import_date", "header": "Month", "agg": None, "grain": "month"}],
        sort=[],
    )
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql, _ = build_table_query(
        rd, PROCESS_CONFIGS, FIELD_COL_MAPS, row_cap=100, resolved_metrics=resolved
    )
    assert "COUNT(*) AS [doc_count]" in sql
    assert "GROUP BY [import_date]" in sql
    assert (
        "DATEFROMPARTS(YEAR(CAST(ImportDate AS date)), MONTH(CAST(ImportDate AS date)), 1) "
        "AS [import_date]" in sql
    )
