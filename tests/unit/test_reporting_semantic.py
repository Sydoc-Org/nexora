# tests/unit/test_reporting_semantic.py
"""Unit tests for nx_lib.reporting.semantic (pure: resolver + aggregate SQL)."""

import pytest

from nx_lib.reporting.semantic import (
    MetricResolveError,
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
