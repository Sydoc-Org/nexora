# tests/unit/test_reporting_sources.py
"""Unit tests for nx_lib.reporting.sources — built-in registry + access filter."""

from nx_lib.reporting.sources import (
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    get_source,
    list_accessible_sources,
)


def test_docprocessing_source_is_registered():
    src = get_source("docprocessing")
    assert src is not None
    assert src["id"] == "docprocessing"
    assert src["kind"] == "curated"
    assert src["permission"] == "reporting.source.docprocessing"


def test_get_unknown_source_returns_none():
    assert get_source("nope") is None


def test_list_accessible_filters_by_permission():
    perms = {"reporting.view", "reporting.source.docprocessing"}
    ids = [s["id"] for s in list_accessible_sources(perms)]
    assert "docprocessing" in ids


def test_list_accessible_excludes_without_permission():
    perms = {"reporting.view"}
    assert list_accessible_sources(perms) == []


def test_row_limit_constants_sane():
    assert 0 < DEFAULT_ROW_LIMIT <= MAX_ROW_LIMIT
