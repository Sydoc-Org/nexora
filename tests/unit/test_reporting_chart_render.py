"""chart_render renders report rows to PNG bytes for mails/exports."""

from nx_lib.reporting.chart_render import render_chart_png

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _defn(columns, chart_type=None):
    d = {"source": "x", "metrics": [{"metric": "doc_count"}], "columns": columns}
    if chart_type:
        d["chartType"] = chart_type
    return d


def test_one_dim_bar_returns_png():
    png = render_chart_png(
        _defn([{"field": "docsource"}]),
        [{"field": "docsource"}, {"field": "doc_count"}],
        [["Scan", 10], ["Mail", 4]],
    )
    assert png and png[:8] == _PNG_MAGIC


def test_two_dims_pivots_to_series_png():
    png = render_chart_png(
        _defn([{"field": "exportdate", "grain": "month"}, {"field": "docsource"}]),
        [{"field": "exportdate"}, {"field": "docsource"}, {"field": "doc_count"}],
        [
            ["2026-04-01", "Scan", 10],
            ["2026-04-01", "Mail", 4],
            ["2026-05-01", "Scan", 12],
            ["2026-05-01", "Mail", 6],
        ],
    )
    assert png and png[:8] == _PNG_MAGIC


def test_two_dims_over_50_raw_rows_pivot_below_max_x_renders():
    # 30 consecutive months x 2 sources = 60 raw rows -> 30 pivoted x-points
    # (<= MAX_X=50). The server caps AFTER pivoting (MAX_X / MAX_SERIES), so
    # this must still render a PNG. This locks the invariant the Simple builder
    # client mountChart must match: its pre-pivot >50-row guard wrongly bailed
    # on the 60 raw rows even though they collapse to 30 x-points.
    rows = []
    for i in range(30):
        y, mo = 2025 + (i // 12), (i % 12) + 1
        month = f"{y}-{mo:02d}-01"
        rows.append([month, "Scan", 10 + i])
        rows.append([month, "Mail", 4 + i])
    png = render_chart_png(
        _defn([{"field": "exportdate", "grain": "month"}, {"field": "docsource"}]),
        [{"field": "exportdate"}, {"field": "docsource"}, {"field": "doc_count"}],
        rows,
    )
    assert png and png[:8] == _PNG_MAGIC


def test_no_dims_returns_none():
    assert render_chart_png(_defn([]), [{"field": "doc_count"}], [[42]]) is None


def test_three_dims_pivots_composite_series_png():
    # dims 2+3 join into one composite series key ("Scan · SAP"), so a
    # three-breakdown result renders instead of returning None.
    cols = [{"field": "exportdate", "grain": "month"}, {"field": "process"}, {"field": "docsource"}]
    png = render_chart_png(
        _defn(cols),
        [*cols, {"field": "doc_count"}],
        [
            ["2026-04-01", "Scan", "SAP", 10],
            ["2026-04-01", "Scan", "Mail", 4],
            ["2026-04-01", "Import", "SAP", 7],
            ["2026-05-01", "Scan", "SAP", 12],
        ],
    )
    assert png and png[:8] == _PNG_MAGIC


def test_empty_rows_returns_none():
    assert (
        render_chart_png(
            _defn([{"field": "docsource"}]), [{"field": "docsource"}, {"field": "doc_count"}], []
        )
        is None
    )
