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
MAX_X_DATE = 400  # a bucketed date axis (53 weeks, 365 days) is still readable as a line


def _num(v):
    """Cell -> float; NULL (no measurement, e.g. a backlog bucket without a
    snapshot) becomes NaN so matplotlib leaves a gap instead of drawing 0."""
    if v is None:
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


MAX_SERIES = 12

# Same 12 colors as the web charts' shared NX_PALETTE (defined in
# _reporting_viz_js.html, duplicated with a sync-comment into
# _reporting_simple_js.html) -- kept byte-for-byte identical, same order, so a
# scheduled/exported PNG never shows different series colors than the same
# report viewed live on screen.
_PALETTE = [
    "#4f46e5",
    "#7c3aed",
    "#0ea5e9",
    "#10b981",
    "#f59e0b",
    "#ef4444",
    "#64748b",
    "#a78bfa",
    "#0891b2",
    "#f97316",
    "#be123c",
    "#94a3b8",
]


def _label(v):
    s = "" if v is None else str(v)
    return s[:10] if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-" else s


def render_chart_png(definition, columns, rows, *, width=8.0, height=4.5, dpi=110, forecast=None):
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
    max_x = MAX_X_DATE if dims[0].get("grain") else MAX_X

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    try:
        if len(dims) == 1 and len(metrics) > 1 and chart_type != "pie":
            # One series per measure (mirrors the Simple pane's per-metric
            # datasets); forecast stays single-metric-only and is skipped here.
            labels = [_label(r[0]) for r in rows[:max_x]]
            n = len(metrics)
            for i, m in enumerate(metrics):
                vals = [_num(r[metric_idx + i]) for r in rows[:max_x]]
                color = _PALETTE[i % len(_PALETTE)]
                name = m.get("metric") or f"metric {i + 1}"
                if chart_type == "line":
                    ax.plot(labels, vals, label=name, color=color, marker="o")
                else:
                    xs = [j + (i - n / 2) * (0.8 / n) + 0.4 / n for j in range(len(labels))]
                    ax.bar(xs, vals, width=0.8 / n, label=name, color=color)
            if chart_type != "line":
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels)
            ax.legend(fontsize=8)
        elif len(dims) == 1:
            data = [(_label(r[0]), _num(r[metric_idx])) for r in rows[:max_x]]
            labels = [d[0] for d in data]
            values = [d[1] for d in data]
            if chart_type == "pie" and len(labels) <= MAX_SERIES:
                ax.pie(values, labels=labels, colors=_PALETTE[: len(labels)], autopct="%1.0f%%")
            elif chart_type == "line":
                ax.plot(labels, values, color=_PALETTE[0], marker="o")
            else:
                ax.bar(labels, values, color=_PALETTE[0])
            if (
                forecast
                and not forecast.get("unavailable")
                and forecast.get("buckets")
                and chart_type in ("line", "bar")
                and len(rows) <= max_x
            ):
                fx = [_label(b) for b in forecast["buckets"]]
                s0 = forecast["series"][0]
                bridge_x, bridge_y = [labels[-1]], [values[-1]]
                ax.plot(
                    bridge_x + fx,
                    bridge_y + list(s0["values"]),
                    color=_PALETTE[0],
                    linestyle="--",
                    marker="o",
                    markersize=3,
                )
                ax.fill_between(
                    bridge_x + fx,
                    bridge_y + list(s0["lower"]),
                    bridge_y + list(s0["upper"]),
                    color=_PALETTE[0],
                    alpha=0.15,
                    linewidth=0,
                )
        else:
            # Multi-dim: grouped bars or lines. Pie is intentionally unsupported here
            # (summing across the second dim would silently lie for distinct-count metrics).
            # pivot: x = dim1 (row order), series = remaining dims joined
            # ("Process · Source", 12 largest by total) — mirrors the Simple-pane
            # client mountChart composite series key.
            x_order: list = []
            series_tot: dict = {}
            cell: dict = {}
            series_metric: dict = {}
            for r in rows:
                x = _label(r[0])
                base = " · ".join(_label(v) for v in r[1 : len(dims)])
                if x not in cell:
                    x_order.append(x)
                    cell[x] = {}
                for i, m in enumerate(metrics):
                    s = f"{base} · {m.get('metric')}" if len(metrics) > 1 else base
                    v = _num(r[metric_idx + i])
                    cell[x][s] = cell[x].get(s, 0) + v
                    series_tot[s] = series_tot.get(s, 0) + v
                    series_metric[s] = i
            x_order = x_order[:MAX_X]
            if len(metrics) > 1:
                # Fair cap per measure (mirrors the Simple-pane pivot): a
                # small-valued measure must not be crowded out entirely.
                per = max(1, MAX_SERIES // len(metrics))
                series = []
                for i in range(len(metrics)):
                    grp = sorted(
                        (s for s in series_tot if series_metric[s] == i),
                        key=series_tot.get,
                        reverse=True,
                    )
                    series.extend(grp[:per])
            else:
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
