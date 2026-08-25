"""chart_render renders report rows to PNG bytes for mails/exports."""

from nx_lib.reporting.chart_render import _PALETTE, MAX_SERIES, render_chart_png

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


def test_palette_covers_the_full_series_cap_with_no_repeats():
    # Finding B: a >7-series breakdown must not silently repeat a color
    # before hitting MAX_SERIES=12 -- _PALETTE (the server-side twin of the
    # web charts' shared NX_PALETTE) must have at least MAX_SERIES distinct
    # entries, so `_PALETTE[i % len(_PALETTE)]` never wraps within one chart.
    assert len(_PALETTE) >= MAX_SERIES
    assert len(set(_PALETTE)) == len(_PALETTE)


def test_render_chart_png_with_forecast_band():
    definition = {
        "columns": [{"field": "d", "grain": "month"}],
        "metrics": [{"metric": "n"}],
        "chartType": "line",
    }
    columns = [{"field": "d"}, {"field": "n"}]
    rows = [[f"2025-{m:02d}-01", 10 + m] for m in range(1, 7)]
    forecast = {
        "anchor": "2025-06-01",
        "grain": "month",
        "method": "trend",
        "horizon": 2,
        "buckets": ["2025-07-01", "2025-08-01"],
        "series": [
            {"field": "n", "values": [17.0, 18.0], "lower": [15.0, 15.5], "upper": [19.0, 20.5]}
        ],
    }
    png = render_chart_png(definition, columns, rows, forecast=forecast)
    assert png and png[:8] == _PNG_MAGIC
    # the forecast must not crash the chartless fallback either
    assert render_chart_png(definition, columns, [], forecast=forecast) is None


def test_one_dim_multi_metric_renders_series_per_measure():
    d = {
        "source": "x",
        "metrics": [
            {"metric": "docs_imported"},
            {"metric": "docs_exported"},
            {"metric": "backlog"},
        ],
        "columns": [{"field": "activity_date", "grain": "month"}],
    }
    png = render_chart_png(
        d,
        [
            {"field": "activity_date"},
            {"field": "docs_imported"},
            {"field": "docs_exported"},
            {"field": "backlog"},
        ],
        [["2026-01-01", 100, 90, 500], ["2026-02-01", 120, 95, 480]],
    )
    assert png and png[:8] == _PNG_MAGIC


def test_two_dims_multi_metric_renders_fair_capped_series():
    d = {
        "source": "x",
        "metrics": [{"metric": "docs_imported"}, {"metric": "docs_exported"}],
        "columns": [{"field": "activity_date", "grain": "month"}, {"field": "processname"}],
    }
    rows = []
    for month in ("2026-01-01", "2026-02-01"):
        for p in range(10):  # 10 processes x 2 metrics = 20 series > MAX_SERIES
            rows.append([month, f"proc{p}", 1000 + p, 5 + p])
    png = render_chart_png(
        d,
        [
            {"field": "activity_date"},
            {"field": "processname"},
            {"field": "docs_imported"},
            {"field": "docs_exported"},
        ],
        rows,
    )
    assert png and png[:8] == _PNG_MAGIC
