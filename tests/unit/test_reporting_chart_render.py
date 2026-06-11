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


def test_no_dims_returns_none():
    assert render_chart_png(_defn([]), [{"field": "doc_count"}], [[42]]) is None


def test_three_dims_returns_none():
    cols = [{"field": "a"}, {"field": "b"}, {"field": "c"}]
    assert (
        render_chart_png(_defn(cols), [*cols, {"field": "doc_count"}], [["x", "y", "z", 1]]) is None
    )


def test_empty_rows_returns_none():
    assert (
        render_chart_png(
            _defn([{"field": "docsource"}]), [{"field": "docsource"}, {"field": "doc_count"}], []
        )
        is None
    )
