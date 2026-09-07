"""Unit tests for nx_lib.reporting.table_query — the generic 'table' provider."""

import pytest

from nx_lib.reporting.table_query import (
    TableQueryError,
    build_distinct_query,
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


def test_build_distinct_query_shape():
    cols = [{"field": "ProcessName", "type": "string", "filterable": True, "sortable": True}]
    sql = build_distinct_query("ProcessName", "dbo.BacklogHistory", cols)
    assert sql == (
        "SELECT DISTINCT TOP (100) [ProcessName] FROM [dbo].[BacklogHistory] "
        "WHERE [ProcessName] IS NOT NULL ORDER BY [ProcessName]"
    )


def test_build_distinct_query_rejects_unknown_or_unfilterable():
    cols = [{"field": "ProcessName", "type": "string", "filterable": False}]
    with pytest.raises(TableQueryError):
        build_distinct_query("ProcessName", "dbo.BacklogHistory", cols)
    with pytest.raises(TableQueryError):
        build_distinct_query("Nope", "dbo.BacklogHistory", cols)


_SNAPSHOT_COLS = [
    {
        "field": "SnapshotAt",
        "type": "datetime",
        "filterable": True,
        "sortable": True,
        "grainable": True,
    },
    {"field": "ProcessName", "type": "string", "filterable": True, "sortable": True},
    {"field": "BacklogCount", "type": "number", "filterable": True, "sortable": True},
]
_SNAPSHOT_METRICS = [{"code": "backlog_total", "aggregation": "sum", "base_field": "BacklogCount"}]


def test_day_grain_truncates_datetime_dimension():
    rd = {"columns": [{"field": "SnapshotAt", "grain": "day"}], "filters": [], "sort": []}
    sql, _ = build_generic_query(
        rd,
        "dbo.BacklogHistory",
        _SNAPSHOT_COLS,
        row_cap=5000,
        resolved_metrics=_SNAPSHOT_METRICS,
    )
    assert "CAST([SnapshotAt] AS date) AS [SnapshotAt]" in sql
    assert "GROUP BY CAST([SnapshotAt] AS date)" in sql


def test_grained_date_dim_excludes_zero_date_sentinel():
    rd = {"columns": [{"field": "SnapshotAt", "grain": "day"}], "filters": [], "sort": []}
    sql, _ = build_generic_query(
        rd,
        "dbo.BacklogHistory",
        _SNAPSHOT_COLS,
        row_cap=5000,
        resolved_metrics=_SNAPSHOT_METRICS,
    )
    assert "([SnapshotAt] IS NULL OR [SnapshotAt] >= '19010101')" in sql


def test_latest_of_with_day_grain_keeps_newest_snapshot_per_bucket():
    rd = {
        "columns": [{"field": "SnapshotAt", "grain": "day"}, {"field": "ProcessName"}],
        "filters": [
            {"field": "SnapshotAt", "op": "between", "value": ["2026-08-01", "2026-08-31"]}
        ],
        "sort": [],
    }
    sql, params = build_generic_query(
        rd,
        "dbo.BacklogHistory",
        _SNAPSHOT_COLS,
        row_cap=5000,
        resolved_metrics=_SNAPSHOT_METRICS,
        latest_of="SnapshotAt",
    )
    assert "[SnapshotAt] IN (SELECT MAX([SnapshotAt]) FROM [dbo].[BacklogHistory]" in sql
    assert "GROUP BY CAST([SnapshotAt] AS date))" in sql
    # filter params appear twice: outer WHERE + the per-bucket MAX subquery
    assert params == ["2026-08-01", "2026-08-31", "2026-08-01", "2026-08-31"]


def test_latest_of_without_date_dimension_constrains_to_global_max():
    rd = {"columns": [{"field": "ProcessName"}], "filters": [], "sort": []}
    sql, _ = build_generic_query(
        rd,
        "dbo.BacklogHistory",
        _SNAPSHOT_COLS,
        row_cap=5000,
        resolved_metrics=_SNAPSHOT_METRICS,
        latest_of="SnapshotAt",
    )
    assert "[SnapshotAt] = (SELECT MAX([SnapshotAt]) FROM [dbo].[BacklogHistory])" in sql


def test_latest_of_skipped_for_raw_date_dimension():
    # grain None: every snapshot instant is its own bucket — no restriction.
    rd = {"columns": [{"field": "SnapshotAt"}], "filters": [], "sort": []}
    sql, _ = build_generic_query(
        rd,
        "dbo.BacklogHistory",
        _SNAPSHOT_COLS,
        row_cap=5000,
        resolved_metrics=_SNAPSHOT_METRICS,
        latest_of="SnapshotAt",
    )
    assert "SELECT MAX(" not in sql


def test_build_distinct_query_label_with_pairs():
    cols = [
        {"field": "ProcessName", "type": "string", "filterable": True, "labelWith": "ClientName"},
        {"field": "ClientName", "type": "string", "filterable": True},
    ]
    sql = build_distinct_query("ProcessName", "dbo.BacklogHistory", cols)
    assert sql == (
        "SELECT DISTINCT TOP (100) [ProcessName], [ClientName] "
        "FROM [dbo].[BacklogHistory] "
        "WHERE [ProcessName] IS NOT NULL ORDER BY [ProcessName], [ClientName]"
    )
    with pytest.raises(TableQueryError):
        build_distinct_query(
            "ProcessName",
            "dbo.BacklogHistory",
            [{"field": "ProcessName", "filterable": True, "labelWith": "Nope"}],
        )


def test_table_source_catalog_passes_advanced_flag_through():
    cols = [
        {"field": "Field", "type": "string", "advanced": True},
        {"field": "FieldKey", "type": "string"},
    ]
    out = table_source_catalog(cols)
    assert out[0]["advanced"] is True
    assert "advanced" not in out[1]
