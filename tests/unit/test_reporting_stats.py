"""Unit tests for the deterministic reporting stats engine (Phase 3a).

Pure: no Flask app, no DB, no network. Exercises exact numeric behaviour over a
(columns, rows) result set — the same shape `_run_sql` / table queries return.
"""

import math

import pytest

from nx_lib.reporting.stats import StatsError, compute_stats

COLS = ["process", "qty"]
ROWS = [["A", 10], ["A", 20], ["B", 30], ["B", None], ["B", 50]]


def test_describe_numeric_column():
    out = compute_stats(COLS, ROWS, {"op": "describe", "columns": ["qty"]})
    q = out["result"]["qty"]
    assert q["count"] == 4 and q["nulls"] == 1
    assert q["min"] == 10 and q["max"] == 50
    assert q["sum"] == 110 and q["mean"] == 27.5
    assert q["median"] == 25.0
    assert math.isclose(q["stddev"], 17.07825127, rel_tol=1e-6)


def test_describe_text_column():
    out = compute_stats(COLS, ROWS, {"op": "describe", "columns": ["process"]})
    q = out["result"]["process"]
    assert q["count"] == 5 and q["distinct"] == 2
    assert q["top"] == "B"  # most frequent


def test_unknown_column_raises():
    with pytest.raises(StatsError):
        compute_stats(COLS, ROWS, {"op": "describe", "columns": ["nope"]})


def test_unknown_op_raises():
    with pytest.raises(StatsError):
        compute_stats(COLS, ROWS, {"op": "bogus"})


def test_group_by_sum_and_mean():
    out = compute_stats(
        COLS,
        ROWS,
        {"op": "group_by", "by": ["process"], "agg": {"qty": ["sum", "mean", "count"]}},
    )
    rows = {tuple(r["group"]): r["values"] for r in out["result"]}
    assert rows[("A",)]["qty"]["sum"] == 30 and rows[("A",)]["qty"]["mean"] == 15.0
    assert rows[("B",)]["qty"]["sum"] == 80 and rows[("B",)]["qty"]["count"] == 2


def test_group_by_unknown_agg_func_raises():
    with pytest.raises(StatsError):
        compute_stats(COLS, ROWS, {"op": "group_by", "by": ["process"], "agg": {"qty": ["bogus"]}})


def test_percentiles_linear_interpolation():
    cols, rows = ["x"], [[i] for i in range(1, 101)]  # 1..100
    out = compute_stats(cols, rows, {"op": "percentiles", "column": "x", "q": [0.5, 0.9, 0.95]})
    r = out["result"]
    assert r["0.5"] == 50.5
    assert math.isclose(r["0.9"], 90.1, rel_tol=1e-9)


def test_percentiles_out_of_range_raises():
    with pytest.raises(StatsError):
        compute_stats(COLS, ROWS, {"op": "percentiles", "column": "qty", "q": [1.5]})


def test_value_counts_top_n():
    out = compute_stats(COLS, ROWS, {"op": "value_counts", "column": "process", "top_n": 1})
    assert out["result"] == [{"value": "B", "count": 3}]


def test_correlation_perfect_positive():
    cols, rows = ["a", "b"], [[1, 2], [2, 4], [3, 6], [4, 8]]
    out = compute_stats(cols, rows, {"op": "correlation", "x": "a", "y": "b"})
    assert math.isclose(out["result"]["r"], 1.0, rel_tol=1e-9)
    assert out["result"]["n"] == 4


def test_correlation_zero_variance_raises():
    cols, rows = ["a", "b"], [[1, 5], [1, 6], [1, 7]]
    with pytest.raises(StatsError):
        compute_stats(cols, rows, {"op": "correlation", "x": "a", "y": "b"})


def test_top_n_descending():
    out = compute_stats(COLS, ROWS, {"op": "top_n", "by": "qty", "n": 2})
    assert [r[1] for r in out["result"]] == [50, 30]


def test_missing_required_arg_raises():
    with pytest.raises(StatsError):
        compute_stats(COLS, ROWS, {"op": "percentiles"})  # no 'column'


def test_group_by_numeric_key_with_nulls_sorts_without_typeerror():
    cols = ["qty", "amount"]
    rows = [[None, 1], [3, 2], [1, 3]]
    out = compute_stats(cols, rows, {"op": "group_by", "by": ["qty"], "agg": {"amount": ["sum"]}})
    groups = [r["group"][0] for r in out["result"]]
    assert groups == [1, 3, None]
