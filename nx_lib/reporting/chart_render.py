"""Server-side chart rendering (matplotlib/Agg) for scheduled mails and XLSX.

Mirrors the web charts' shapes and caps: one dimension -> bar/line/pie on that
dimension; two dimensions -> first dim is the X axis, second becomes series
(grouped bars or one line per series); three or more dimensions, no metrics,
or no rows -> None (callers fall back to a chartless artifact). Caps mirror
the frontend: 50 X values, 12 series.
"""

import io
import os

# Service accounts (IIS app pool, Task Scheduler) have no writable HOME; the
# font cache must land inside var/ (already in the Defender exclusion). Must
# be set before the first matplotlib import.
_MPL_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "var", "mpl-cache"
)
os.makedirs(_MPL_CACHE, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", _MPL_CACHE)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MAX_X = 50
MAX_SERIES = 12

# Same 12 colors as the web charts (SIMPLE_PALETTE / ReportingViz).
_PALETTE = [
    "#4338ca",
    "#2563eb",
    "#0891b2",
    "#059669",
    "#65a30d",
    "#ca8a04",
    "#dc2626",
    "#db2777",
    "#7c3aed",
    "#0d9488",
    "#ea580c",
    "#4f46e5",
]


def _label(v):
    s = "" if v is None else str(v)
    return s[:10] if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-" else s


def render_chart_png(definition, columns, rows, *, width=8.0, height=4.5, dpi=110):
    """Render `rows` (aligned to `columns`) as a PNG per `definition`.

    Returns PNG bytes, or None when the result shape has no sensible chart.
    """
    dims = list(definition.get("columns") or [])
    metrics = list(definition.get("metrics") or [])
    if not metrics or not rows or not dims:
        return None
    # Assumes query engine places metrics as trailing columns (dims first).
    metric_idx = len(columns) - len(metrics)
    chart_type = definition.get("chartType") or ("line" if dims[0].get("grain") else "bar")

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    try:
        if len(dims) == 1:
            data = [(_label(r[0]), float(r[metric_idx] or 0)) for r in rows[:MAX_X]]
            labels = [d[0] for d in data]
            values = [d[1] for d in data]
            if chart_type == "pie" and len(labels) <= MAX_SERIES:
                ax.pie(values, labels=labels, colors=_PALETTE[: len(labels)], autopct="%1.0f%%")
            elif chart_type == "line":
                ax.plot(labels, values, color=_PALETTE[0], marker="o")
            else:
                ax.bar(labels, values, color=_PALETTE[0])
        else:
            # Multi-dim: grouped bars or lines. Pie is intentionally unsupported here
            # (summing across the second dim would silently lie for distinct-count metrics).
            # pivot: x = dim1 (row order), series = remaining dims joined
            # ("Process · Source", 12 largest by total) — mirrors the Simple-pane
            # client mountChart composite series key.
            x_order, series_tot, cell = [], {}, {}
            for r in rows:
                x = _label(r[0])
                s = " · ".join(_label(v) for v in r[1 : len(dims)])
                v = float(r[metric_idx] or 0)
                if x not in cell:
                    x_order.append(x)
                    cell[x] = {}
                cell[x][s] = cell[x].get(s, 0) + v
                series_tot[s] = series_tot.get(s, 0) + v
            x_order = x_order[:MAX_X]
            series = sorted(series_tot, key=series_tot.get, reverse=True)[:MAX_SERIES]
            n = max(len(series), 1)
            for i, s in enumerate(series):
                vals = [cell[x].get(s, 0) for x in x_order]
                color = _PALETTE[i % len(_PALETTE)]
                if chart_type == "line":
                    ax.plot(x_order, vals, label=s, color=color, marker="o")
                else:
                    xs = [j + (i - n / 2) * (0.8 / n) + 0.4 / n for j in range(len(x_order))]
                    ax.bar(xs, vals, width=0.8 / n, label=s, color=color)
            if chart_type != "line":
                ax.set_xticks(range(len(x_order)))
                ax.set_xticklabels(x_order)
            ax.legend(fontsize=8)
        if chart_type != "pie":
            ax.tick_params(axis="x", labelrotation=45, labelsize=8)
            ax.tick_params(axis="y", labelsize=8)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()
    finally:
        plt.close(fig)
