# tests/unit/test_reporting_sources.py
"""Unit tests for nx_lib.reporting.sources — built-in registry + access filter."""

from nx_lib.reporting.sources import (
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
    accessible,
    code_sources,
    merge_sources,
)


def test_row_limit_constants_sane():
    assert 0 < DEFAULT_ROW_LIMIT <= MAX_ROW_LIMIT


# --- A3: DB registry merge ---


def test_code_sources_includes_docprocessing_with_provider():
    by_id = {s["id"]: s for s in code_sources()}
    assert by_id["docprocessing"]["provider"] == "docprocessing"


def test_merge_with_no_db_rows_returns_defaults():
    eff = merge_sources(code_sources(), [])
    assert "docprocessing" in {s["id"] for s in eff}


def test_merge_db_row_overrides_label_and_can_disable():
    eff = merge_sources(code_sources(), [{"code": "docprocessing", "label": "Renamed"}])
    assert next(s for s in eff if s["id"] == "docprocessing")["label"] == "Renamed"
    # Disabling drops it from the effective set.
    eff2 = merge_sources(code_sources(), [{"code": "docprocessing", "enabled": False}])
    assert "docprocessing" not in {s["id"] for s in eff2}


def test_merge_db_row_registers_new_source():
    row = {
        "code": "gen_x",
        "kind": "curated",
        "label": "Generali X",
        "permission": "reporting.source.generali.x",
        "provider": "table",
        "engine": "generali",
        "baseObject": "Generali.dbo.SomeView",
        "enabled": True,
        "sortOrder": 5,
    }
    eff = merge_sources(code_sources(), [row])
    new = next(s for s in eff if s["id"] == "gen_x")
    assert new["provider"] == "table" and new["engine"] == "generali"
    # SortOrder 5 puts it before docprocessing (default 100).
    assert eff[0]["id"] == "gen_x"


def test_merge_none_values_do_not_clobber_defaults():
    eff = merge_sources(code_sources(), [{"code": "docprocessing", "label": None}])
    assert next(s for s in eff if s["id"] == "docprocessing")["label"] == "Document Processing"


def test_accessible_filters_effective_by_permission():
    eff = merge_sources(code_sources(), [])
    assert accessible(eff, {"reporting.source.docprocessing.use"})
    assert accessible(eff, {"reporting.view"}) == []
