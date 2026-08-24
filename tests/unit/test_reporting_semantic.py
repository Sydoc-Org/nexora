# tests/unit/test_reporting_semantic.py
"""Unit tests for nx_lib.reporting.semantic (pure: resolver + aggregate SQL)."""

import pytest

from nx_lib.reporting.semantic import (
    MetricResolveError,
    build_aggregate_sql,
    metric_select_expr,
    resolve_metrics,
)

REGISTRY = {
    "doc_count": {"aggregation": "count", "base_field": None},
    "pages_sum": {"aggregation": "sum", "base_field": "pages"},
    "type_distinct": {"aggregation": "count_distinct", "base_field": "doctype"},
}
CATALOG = {"doctype", "status", "pages"}


def test_resolve_count_ignores_base_field():
    out = resolve_metrics([{"metric": "doc_count"}], REGISTRY, CATALOG)
    assert out == [{"code": "doc_count", "aggregation": "count", "base_field": None}]


def test_resolve_sum_requires_base_field_in_catalog():
    out = resolve_metrics([{"metric": "pages_sum"}], REGISTRY, CATALOG)
    assert out == [{"code": "pages_sum", "aggregation": "sum", "base_field": "pages"}]


def test_resolve_unknown_metric_raises():
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "nope"}], REGISTRY, CATALOG)


def test_resolve_base_field_not_in_catalog_raises():
    reg = {"bad": {"aggregation": "sum", "base_field": "secret_col"}}
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "bad"}], reg, CATALOG)


def test_resolve_duplicate_metric_raises():
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "doc_count"}, {"metric": "doc_count"}], REGISTRY, CATALOG)


def test_resolve_unsafe_code_raises():
    reg = {"a]b": {"aggregation": "count", "base_field": None}}
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "a]b"}], reg, CATALOG)


def test_resolve_unsafe_base_field_raises():
    # base_field is bracketed into the aggregate expr; an unsafe identifier must
    # raise even when it is (mis)configured into the catalog set.
    reg = {"bad": {"aggregation": "sum", "base_field": "a]b"}}
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "bad"}], reg, {"a]b"})


def _bracket(field):
    return f"[{field}]"


def test_metric_select_expr_count_is_count_star():
    r = {"code": "doc_count", "aggregation": "count", "base_field": None}
    assert metric_select_expr(r, _bracket) == "COUNT(*) AS [doc_count]"


def test_metric_select_expr_sum_and_distinct():
    assert (
        metric_select_expr(
            {"code": "pages_sum", "aggregation": "sum", "base_field": "pages"}, _bracket
        )
        == "SUM([pages]) AS [pages_sum]"
    )
    assert (
        metric_select_expr(
            {"code": "t_d", "aggregation": "count_distinct", "base_field": "doctype"}, _bracket
        )
        == "COUNT(DISTINCT [doctype]) AS [t_d]"
    )


def test_build_aggregate_sql_groups_by_dims_and_orders_by_metric():
    resolved = [{"code": "doc_count", "aggregation": "count", "base_field": None}]
    sql = build_aggregate_sql(
        inner_from="[Db].[dbo].[T]",
        dim_fields=["status"],
        resolved_metrics=resolved,
        sort=[{"field": "doc_count", "dir": "desc"}],
        cap=100,
    )
    assert sql == (
        "SELECT TOP (100) [status], COUNT(*) AS [doc_count] "
        "FROM [Db].[dbo].[T] GROUP BY [status] ORDER BY [doc_count] DESC"
    )


def test_build_aggregate_sql_rejects_sort_field_not_projected():
    with pytest.raises(MetricResolveError):
        build_aggregate_sql(
            inner_from="[T]",
            dim_fields=["status"],
            resolved_metrics=[{"code": "doc_count", "aggregation": "count", "base_field": None}],
            sort=[{"field": "ghost", "dir": "asc"}],
            cap=10,
        )


def test_build_aggregate_sql_zero_dims_omits_group_by():
    sql = build_aggregate_sql(
        inner_from="(SELECT 1 AS [_one] FROM [T]) t",
        dim_fields=[],
        resolved_metrics=[{"code": "doc_count", "aggregation": "count", "base_field": None}],
        sort=[],
        cap=100,
    )
    assert sql == "SELECT TOP (100) COUNT(*) AS [doc_count] FROM (SELECT 1 AS [_one] FROM [T]) t"
    assert "GROUP BY" not in sql


def test_build_aggregate_sql_zero_dims_sort_by_metric_allowed():
    sql = build_aggregate_sql(
        inner_from="[V]",
        dim_fields=[],
        resolved_metrics=[{"code": "total", "aggregation": "sum", "base_field": "amount"}],
        sort=[{"field": "total", "dir": "desc"}],
        cap=10,
    )
    assert sql.endswith("ORDER BY [total] DESC")


# ---- drop_columns_shadowing_distinct_metrics --------------------------------

from nx_lib.reporting.semantic import drop_columns_shadowing_distinct_metrics  # noqa: E402

_SHADOW_REGISTRY = {
    "doc_count": {"aggregation": "count", "base_field": None},
    "workitem_count": {"aggregation": "count_distinct", "base_field": "workitem_id"},
}


def test_drops_column_matching_distinct_metric_base_field():
    rd = {
        "columns": [{"field": "processname"}, {"field": "workitem_id"}],
        "metrics": [{"metric": "workitem_count"}],
    }
    dropped = drop_columns_shadowing_distinct_metrics(rd, _SHADOW_REGISTRY)
    assert dropped == ["workitem_id"]
    assert [c["field"] for c in rd["columns"]] == ["processname"]


def test_drop_can_empty_columns_for_grand_total():
    rd = {
        "columns": [{"field": "workitem_id"}],
        "metrics": [{"metric": "workitem_count"}],
    }
    assert drop_columns_shadowing_distinct_metrics(rd, _SHADOW_REGISTRY) == ["workitem_id"]
    assert rd["columns"] == []


def test_plain_count_metric_never_drops_columns():
    # "List distinct workitem ids with their row counts" stays intact.
    rd = {
        "columns": [{"field": "workitem_id"}],
        "metrics": [{"metric": "doc_count"}],
    }
    assert drop_columns_shadowing_distinct_metrics(rd, _SHADOW_REGISTRY) == []
    assert [c["field"] for c in rd["columns"]] == ["workitem_id"]


def test_no_metrics_is_a_no_op():
    rd = {"columns": [{"field": "workitem_id"}], "metrics": []}
    assert drop_columns_shadowing_distinct_metrics(rd, _SHADOW_REGISTRY) == []
    assert rd["columns"] == [{"field": "workitem_id"}]


def test_unknown_metric_code_is_ignored():
    rd = {
        "columns": [{"field": "workitem_id"}],
        "metrics": [{"metric": "nope"}],
    }
    assert drop_columns_shadowing_distinct_metrics(rd, _SHADOW_REGISTRY) == []


# ---------------------------------------------------------------------------
# Date-anchored metrics (imported/exported/backlog, migration 0067)
# ---------------------------------------------------------------------------

_ANCHORED_REGISTRY = {
    "docs_imported": {"aggregation": "sum", "base_field": None, "anchor": "import_date"},
    "pages_imported": {"aggregation": "sum", "base_field": "pagecount", "anchor": "import_date"},
    "backlog": {"aggregation": "sum", "base_field": None, "anchor": "backlog"},
    "bad_agg": {"aggregation": "avg", "base_field": None, "anchor": "import_date"},
    "bad_base": {"aggregation": "sum", "base_field": "nope", "anchor": "export_date"},
}


def test_resolve_anchored_metric_aliases_counter_to_code():
    out = resolve_metrics(
        [{"metric": "docs_imported"}, {"metric": "pages_imported"}, {"metric": "backlog"}],
        _ANCHORED_REGISTRY,
        {"pagecount"},
    )
    assert out[0] == {
        "code": "docs_imported",
        "aggregation": "sum",
        "base_field": "docs_imported",
        "anchor": "import_date",
        "value_field": None,
    }
    assert out[1]["base_field"] == "pages_imported"  # outer SUMs the alias
    assert out[1]["value_field"] == "pagecount"  # legs read the real column
    assert out[2]["anchor"] == "backlog"


def test_resolve_anchored_metric_rejects_non_sum_and_bad_value_field():
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "bad_agg"}], _ANCHORED_REGISTRY, {"pagecount"})
    with pytest.raises(MetricResolveError):
        resolve_metrics([{"metric": "bad_base"}], _ANCHORED_REGISTRY, {"pagecount"})
