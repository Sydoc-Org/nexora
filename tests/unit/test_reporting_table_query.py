"""Unit tests for nx_lib.reporting.table_query — the generic 'table' provider."""

import pytest

from nx_lib.reporting.table_query import (
    TableQueryError,
    build_generic_query,
    table_source_catalog,
)

_COLUMNS = [
    {"field": "client", "label": "Client", "type": "string", "filterable": True, "sortable": True},
    {"field": "amount", "label": "Amount", "type": "number", "filterable": True, "sortable": True},
]


def _rd(**over):
    rd = {
        "schemaVersion": 1,
        "source": "x",
        "visualization": "table",
        "title": "t",
        "columns": [{"field": "client"}, {"field": "amount"}],
        "filters": [],
        "sort": [],
        "scope": {},
        "rowLimit": 100,
    }
    rd.update(over)
    return rd


def test_catalog_normalizes_columns():
    cat = table_source_catalog([{"field": "a"}, {"column": "b", "label": "B"}, {}])
    fields = [c["field"] for c in cat]
    assert fields == ["a", "b"]  # the empty entry is skipped
    assert cat[1]["label"] == "B" and cat[1]["filterable"] is True


def test_basic_select_projects_and_caps():
    sql, params = build_generic_query(_rd(), "Db.dbo.View", _COLUMNS, row_cap=500)
    assert sql.startswith("SELECT TOP (500) [client], [amount] FROM [Db].[dbo].[View]")
    assert params == []


def test_filters_parameterized_and_like_escaped():
    rd = _rd(
        filters=[
            {"field": "client", "op": "contains", "value": "Ac%me"},
            {"field": "amount", "op": "gte", "value": 100},
        ]
    )
    sql, params = build_generic_query(rd, "dbo.V", _COLUMNS, row_cap=10)
    assert "[client] LIKE ?" in sql and "[amount] >= ?" in sql
    assert params[0] == "%Ac[%]me%" and params[1] == 100


def test_in_and_between_and_nulls():
    rd = _rd(
        filters=[
            {"field": "client", "op": "in", "value": ["A", "B"]},
            {"field": "amount", "op": "between", "value": [1, 9]},
            {"field": "client", "op": "is_not_null"},
        ]
    )
    sql, params = build_generic_query(rd, "dbo.V", _COLUMNS, row_cap=10)
    assert "[client] IN (?,?)" in sql
    assert "[amount] BETWEEN ? AND ?" in sql
    assert "[client] IS NOT NULL" in sql
    assert params == ["A", "B", 1, 9]


def test_sort_direction():
    sql, _ = build_generic_query(
        _rd(sort=[{"field": "amount", "dir": "desc"}]), "dbo.V", _COLUMNS, row_cap=10
    )
    assert sql.rstrip().endswith("ORDER BY [amount] DESC")


def test_unknown_column_rejected():
    with pytest.raises(TableQueryError):
        build_generic_query(_rd(columns=[{"field": "evil"}]), "dbo.V", _COLUMNS, row_cap=10)


def test_unsafe_base_object_rejected():
    with pytest.raises(TableQueryError):
        build_generic_query(_rd(), "dbo.V; DROP TABLE x", _COLUMNS, row_cap=10)


def test_unsafe_identifier_in_catalog_rejected():
    bad_cols = [{"field": "a]; DROP", "filterable": True, "sortable": True}]
    rd = _rd(columns=[{"field": "a]; DROP"}])
    with pytest.raises(TableQueryError):
        build_generic_query(rd, "dbo.V", table_source_catalog(bad_cols), row_cap=10)


def test_generic_aggregate_groups_and_aggregates():
    from nx_lib.reporting.table_query import build_generic_query

    rd = {
        "columns": [{"field": "client"}],
        "filters": [{"field": "client", "op": "eq", "value": "ACME"}],
        "sort": [{"field": "amount_sum", "dir": "desc"}],
    }
    cols = [
        {"field": "client", "type": "string"},
        {"field": "amount", "type": "number"},
    ]
    resolved = [{"code": "amount_sum", "aggregation": "sum", "base_field": "amount"}]
    sql, params = build_generic_query(
        rd, "Db.dbo.Sales", cols, row_cap=100, resolved_metrics=resolved
    )
    assert sql == (
        "SELECT TOP (100) [client], SUM([amount]) AS [amount_sum] "
        "FROM [Db].[dbo].[Sales] WHERE [client] = ? "
        "GROUP BY [client] ORDER BY [amount_sum] DESC"
    )
    assert params == ["ACME"]


def test_zero_dim_metric_global_total_generic():
    rd = _rd(columns=[], sort=[])
    resolved = [{"code": "n", "aggregation": "count", "base_field": None}]
    sql, params = build_generic_query(
        rd, "Db.dbo.V", _COLUMNS, row_cap=100, resolved_metrics=resolved
    )
    assert sql == "SELECT TOP (100) COUNT(*) AS [n] FROM [Db].[dbo].[V]"
    assert params == []


def test_zero_dim_without_metrics_still_rejected_generic():
    rd = _rd(columns=[], sort=[])
    with pytest.raises(TableQueryError):
        build_generic_query(rd, "Db.dbo.V", _COLUMNS, row_cap=100)


def test_build_conditions_rejects_unresolved_token_value():
    from nx_lib.reporting.table_query import _build_conditions

    rd = {"filters": [{"field": "client", "op": "between", "value": {"token": "last_month"}}]}
    with pytest.raises(TableQueryError, match="unresolved"):
        _build_conditions(rd, {"client": {"field": "client"}})


def test_generic_aggregate_three_dims():
    """Three dimensions GROUP BY all three, in definition order."""
    _three_cols = [
        {"field": "colA", "type": "string"},
        {"field": "colB", "type": "string"},
        {"field": "colC", "type": "string"},
    ]
    rd = {
        "columns": [{"field": "colA"}, {"field": "colB"}, {"field": "colC"}],
        "filters": [],
        "sort": [{"field": "n", "dir": "desc"}],
    }
    resolved = [{"code": "n", "aggregation": "count", "base_field": None}]
    sql, params = build_generic_query(
        rd, "Db.dbo.SomeTable", _three_cols, row_cap=100, resolved_metrics=resolved
    )
    assert "GROUP BY [colA], [colB], [colC]" in sql


def test_zero_dim_latest_of_constrains_to_max_bucket():
    rd = {
        "columns": [],
        "filters": [
            {"field": "SnapshotAt", "op": "between", "value": ["2026-08-01", "2026-08-31"]}
        ],
        "sort": [],
    }
    cols = [
        {
            "field": "SnapshotAt",
            "type": "datetime",
            "filterable": True,
            "sortable": True,
            "grainable": True,
        },
        {"field": "BacklogCount", "type": "number", "filterable": True, "sortable": True},
    ]
    metrics = [{"code": "backlog_total", "aggregation": "sum", "base_field": "BacklogCount"}]
    sql, params = build_generic_query(
        rd,
        "dbo.BacklogHistory",
        cols,
        row_cap=5000,
        resolved_metrics=metrics,
        latest_of="SnapshotAt",
    )
    assert "[SnapshotAt] = (SELECT MAX([SnapshotAt]) FROM [dbo].[BacklogHistory]" in sql
    # filter params appear twice: outer WHERE + the MAX() subquery's WHERE
    assert params == ["2026-08-01", "2026-08-31", "2026-08-01", "2026-08-31"]


def test_latest_of_ignored_with_dimensions():
    rd = {"columns": [{"field": "SnapshotAt", "grain": "day"}], "filters": [], "sort": []}
    cols = [
        {
            "field": "SnapshotAt",
            "type": "datetime",
            "filterable": True,
            "sortable": True,
            "grainable": True,
        },
        {"field": "BacklogCount", "type": "number", "filterable": True, "sortable": True},
    ]
    metrics = [{"code": "backlog_total", "aggregation": "sum", "base_field": "BacklogCount"}]
    sql, _ = build_generic_query(
        rd,
        "dbo.BacklogHistory",
        cols,
        row_cap=5000,
        resolved_metrics=metrics,
        latest_of="SnapshotAt",
    )
    assert "SELECT MAX(" not in sql
