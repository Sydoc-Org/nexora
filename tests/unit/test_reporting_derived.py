"""Unit tests for nx_lib.reporting.derived — layout measures over a run result.

Pure: no Flask, no DB. Rows are the (columns, rows) shape /api/reporting/run
returns: columns [{field, header}], rows positional.
"""

import math

import pytest

from nx_lib.reporting.derived import compute_derived

COLS = [{"field": "import_date", "header": "Import date"}, {"field": "doc_count", "header": "Docs"}]
ROWS = [["2026-01-01", 10], ["2026-01-02", 20], ["2026-01-03", 30], ["2026-01-04", 40]]
RD = {"columns": [{"field": "import_date", "grain": "day"}], "metrics": [{"metric": "doc_count"}]}


def _layout(*measures):
    return {
        "kind": "layout",
        "schemaVersion": 1,
        "title": "t",
        "measures": list(measures),
        "tiles": [],
    }


def test_mean_min_max_range_stddev_percentile_over_metric_column():
    out = compute_derived(
        _layout(
            {"id": "a", "op": "mean"},
            {"id": "b", "op": "minmax"},
            {"id": "c", "op": "range"},
            {"id": "d", "op": "stddev"},
            {"id": "e", "op": "percentile", "q": 0.5},
        ),
        RD,
        COLS,
        ROWS,
    )
    assert out["a"] == {"op": "mean", "value": 25.0, "n": 4}
    assert out["b"] == {"op": "minmax", "min": 10.0, "max": 40.0, "n": 4}
    assert out["c"] == {"op": "range", "value": 30.0, "n": 4}
    assert math.isclose(out["d"]["value"], 12.909944, rel_tol=1e-6) and out["d"]["n"] == 4
    assert out["e"] == {"op": "percentile", "value": 25.0, "n": 4, "q": 0.5}


def test_current_is_latest_date_bucket_for_single_date_dimension():
    out = compute_derived(_layout({"id": "cur", "op": "current"}), RD, COLS, ROWS)
    assert out["cur"] == {"op": "current", "value": 40.0, "n": 4}


def test_current_is_sum_when_dimension_is_not_a_date():
    rd = {"columns": [{"field": "doctype"}], "metrics": [{"metric": "doc_count"}]}
    cols = [{"field": "doctype", "header": "Type"}, {"field": "doc_count", "header": "Docs"}]
    out = compute_derived(_layout({"id": "cur", "op": "current"}), rd, cols, ROWS)
    assert out["cur"] == {"op": "current", "value": 100.0, "n": 4}


def test_unknown_metric_falls_back_to_first_numeric_column():
    rd = {"columns": [{"field": "doctype"}], "metrics": []}
    cols = [{"field": "doctype", "header": "Type"}, {"field": "pages", "header": "Pages"}]
    out = compute_derived(_layout({"id": "m", "op": "mean"}), rd, cols, [["A", 2], ["B", 4]])
    assert out["m"]["value"] == 3.0


def test_no_numeric_column_reports_unavailable_per_measure():
    cols = [{"field": "a", "header": "A"}, {"field": "b", "header": "B"}]
    out = compute_derived(
        _layout({"id": "m", "op": "mean"}), {"columns": [], "metrics": []}, cols, [["x", "y"]]
    )
    assert out["m"] == {"op": "mean", "unavailable": "no_numeric_column"}


def test_empty_rows_reports_unavailable_no_rows():
    out = compute_derived(
        _layout({"id": "m", "op": "mean"}, {"id": "p", "op": "percentile", "q": 0.9}), RD, COLS, []
    )
    assert out["m"] == {"op": "mean", "unavailable": "no_rows"}
    assert out["p"] == {"op": "percentile", "unavailable": "no_rows"}


def test_null_and_non_numeric_cells_are_dropped_not_fatal():
    rows = [["2026-01-01", 10], ["2026-01-02", None], ["2026-01-03", "n/a"], ["2026-01-04", 30]]
    out = compute_derived(_layout({"id": "m", "op": "mean"}), RD, COLS, rows)
    assert out["m"] == {"op": "mean", "value": 20.0, "n": 2}


def test_single_row_stddev_is_zero():
    out = compute_derived(_layout({"id": "s", "op": "stddev"}), RD, COLS, ROWS[:1])
    assert out["s"] == {"op": "stddev", "value": 0.0, "n": 1}


def test_too_many_rows_reports_unavailable_rows():
    from nx_lib.reporting.derived import MAX_ROWS

    rows = [["2026-01-01", 1]] * (MAX_ROWS + 1)
    out = compute_derived(_layout({"id": "m", "op": "mean"}), RD, COLS, rows)
    assert out["m"] == {"op": "mean", "unavailable": "too_many_rows"}


def test_unknown_op_raises_value_error():
    with pytest.raises(ValueError):
        compute_derived(_layout({"id": "m", "op": "delta"}), RD, COLS, ROWS)
