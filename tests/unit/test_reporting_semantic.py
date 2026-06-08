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
