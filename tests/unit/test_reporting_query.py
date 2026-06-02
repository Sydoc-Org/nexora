# tests/unit/test_reporting_query.py
"""Unit tests for nx_lib.reporting.query.build_table_query (pure)."""

import pytest

from nx_lib.reporting.query import QueryBuildError, build_table_query

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
