"""Unit tests for nx_lib.reporting.contribution — contribution analysis maths."""

import pytest

from nx_lib.reporting.contribution import (
    contribution_rows,
    fill_shares,
    is_ratio_metric,
    pick_dimensions,
    single_dimension_definition,
)
from nx_lib.reporting.sources import MAX_ROW_LIMIT


def _f(field, type_="string", label=None):
    return {
        "field": field,
        "label": label or field,
        "type": type_,
        "filterable": True,
        "sortable": True,
        "grainable": type_ in ("date", "datetime"),
    }


CATALOG = [
    _f("doctype"),
    _f("import_date", "date"),
    _f("processname", label="Process"),
    _f("pages", "number"),
    _f("status"),
    _f("workitem_id"),
    _f("client"),
]


def test_pick_dimensions_process_first_then_strings_in_catalog_order():
    picked = pick_dimensions(CATALOG, [])
    assert [d["field"] for d in picked] == ["processname", "doctype", "status"]


def test_pick_dimensions_skips_eq_filtered_and_workitem_id():
    filters = [
        {"field": "doctype", "op": "eq", "value": "Invoice"},
        {"field": "status", "op": "in", "value": ["a", "b"]},
    ]
    picked = pick_dimensions(CATALOG, filters)
    assert [d["field"] for d in picked] == ["processname", "status", "client"]


def test_pick_dimensions_without_processname_and_with_cap():
    cat = [_f("a"), _f("b"), _f("c"), _f("d")]
    assert [d["field"] for d in pick_dimensions(cat, [], cap=2)] == ["a", "b"]
    assert pick_dimensions([_f("n", "number")], []) == []


def test_single_dimension_definition_is_a_clean_deep_copy():
    rd = {
        "schemaVersion": 1,
        "source": "docprocessing",
        "title": "T",
        "columns": [{"field": "import_date", "grain": "month"}],
        "filters": [{"field": "import_date", "op": "between", "value": {"token": "this_month"}}],
        "sort": [{"field": "import_date", "dir": "asc"}],
        "metrics": [{"metric": "doc_count"}, {"metric": "pages_sum"}],
        "forecast": {"enabled": True},
        "compare": True,
        "rowLimit": 50,
        "scope": {"clients": ["a"], "processes": []},
    }
    out = single_dimension_definition(rd, "doctype", "doc_count")
    assert out["columns"] == [{"field": "doctype"}]
    assert out["metrics"] == [{"metric": "doc_count"}]
    assert out["sort"] == []
    assert "forecast" not in out and "compare" not in out
    assert out["rowLimit"] == MAX_ROW_LIMIT
    assert out["filters"] == rd["filters"] and out["filters"] is not rd["filters"]
    assert out["scope"] == rd["scope"]
    assert rd["columns"][0]["grain"] == "month"  # original untouched


def test_contribution_rows_joins_sorts_and_folds():
    current = [["a", 400], ["b", 50], [None, 12], ["c", 5], ["d", 1]]
    prior = [["a", 250], ["b", 80], [None, 30], ["e", 7]]
    rows = contribution_rows(current, prior, top=2)
    assert [r["value"] for r in rows] == ["a", "b", "(other)"]
    assert rows[0] == {"value": "a", "current": 400, "prior": 250, "delta": 150, "share": None}
    assert rows[1]["delta"] == -30
    other = rows[2]
    # (empty) -18, c +5, d +1, e -7  → current 18, prior 37, delta -19
    assert (other["current"], other["prior"], other["delta"]) == (18, 37, -19)


def test_contribution_rows_no_fold_when_within_top():
    rows = contribution_rows([["a", 1]], [["b", 2]], top=8)
    assert [r["value"] for r in rows] == ["b", "a"]  # |-2| before |+1|
    assert rows[0] == {"value": "b", "current": 0, "prior": 2, "delta": -2, "share": None}


def test_contribution_rows_empty_label_and_decimal_strings():
    from decimal import Decimal

    rows = contribution_rows([[None, Decimal("2.5")]], [], top=8)
    assert rows == [{"value": "(empty)", "current": 2.5, "prior": 0, "delta": 2.5, "share": None}]


def test_fill_shares_sets_fraction_or_null():
    dims = [
        {
            "field": "x",
            "label": "X",
            "rows": [
                {"value": "a", "current": 4, "prior": 1, "delta": 3, "share": None},
                {"value": "b", "current": 0, "prior": 1, "delta": -1, "share": None},
            ],
        }
    ]
    fill_shares(dims, 2, False)
    assert dims[0]["rows"][0]["share"] == pytest.approx(1.5)
    assert dims[0]["rows"][1]["share"] == pytest.approx(-0.5)
    fill_shares(dims, 0, False)
    assert all(r["share"] is None for r in dims[0]["rows"])
    fill_shares(dims, 2, True)
    assert all(r["share"] is None for r in dims[0]["rows"])


@pytest.mark.parametrize(
    "agg,expected",
    [
        ("count", False),
        ("sum", False),
        ("avg", True),
        ("min", True),
        ("max", True),
        ("count_distinct", True),
    ],
)
def test_is_ratio_metric(agg, expected):
    assert is_ratio_metric({"aggregation": agg}) is expected
    assert is_ratio_metric(None) is False
