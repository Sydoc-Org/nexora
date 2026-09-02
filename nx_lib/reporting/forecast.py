"""Pure-stdlib forecasting over an aggregated report time series (#168).

OLS linear trend + additive seasonal indices (classical decomposition) with
textbook regression prediction intervals. Deliberately NOT statsmodels: the
WSGI app takes no numpy/scipy/pandas dependency (same rule as stats.py), and
the short series reporting produces gain nothing from SARIMA-grade machinery.
The engine hides behind compute_forecast's response contract, so a heavier
library can replace it later without touching any caller.
# ponytail: classical decomposition, swap in statsmodels ETS behind
# compute_forecast if forecast quality ever measurably hurts.
"""

import datetime
import math

MIN_POINTS = 5  # trend-only floor; seasonal needs 2*period (see forecast_series)
MAX_HORIZON = 60
AUTO_HORIZON_CAP = 30

# Additive seasonal period per grain; week/year stay trend-only (a 52-week
# season would need 2+ years of weekly buckets to fit — not worth the wait).
_SEASON_PERIODS = {"day": 7, "month": 12, "quarter": 4}

# Two-sided 95% t-quantiles by degrees of freedom (df 1..30, then z≈1.96).
_T_975 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def _t_quantile(df):
    return _T_975.get(df, 1.96 if df > 30 else 12.706)


def _season_pos(d, grain):
    """Calendar season position of bucket date `d` (not i mod period, so gaps
    and partial periods cannot shift the cycle)."""
    if grain == "day":
        return d.weekday()
    if grain == "month":
        return d.month - 1
    if grain == "quarter":
        return (d.month - 1) // 3
    return None


def _add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    return datetime.date(total // 12, total % 12 + 1, 1)


def _step(d, grain):
    """The bucket start immediately after `d` for the given grain (mirrors the
    SQL grain buckets: Monday-anchored weeks, first-of-period months etc.)."""
    if grain == "day":
        return d + datetime.timedelta(days=1)
    if grain == "week":
        return d + datetime.timedelta(days=7)
    if grain == "month":
        return _add_months(d, 1)
    if grain == "quarter":
        return _add_months(d, 3)
    if grain == "year":
        return datetime.date(d.year + 1, 1, 1)
    raise ValueError(f"unsupported grain: {grain!r}")


def _next_buckets(last, grain, n):
    out, d = [], last
    for _ in range(n):
        d = _step(d, grain)
        out.append(d)
    return out


def forecast_series(dates, values, grain, horizon):
    """Fit trend(+season) on one contiguous bucket series and project it.

    dates: list[datetime.date] bucket starts (contiguous — caller zero-fills).
    Returns (future_dates, yhat, lower, upper, method) or None when the
    history is too short or degenerate. Bounds are a 95% regression
    prediction interval that widens with the horizon; for an all-nonnegative
    history, projections and bounds are clamped at zero (counts can't dip
    below nothing).
    """
    n = len(values)
    if n < MIN_POINTS or horizon < 1 or len(dates) != n:
        return None
    xbar = (n - 1) / 2
    ybar = sum(values) / n
    sxx = sum((i - xbar) ** 2 for i in range(n))
    if sxx == 0:
        return None
    b = sum((i - xbar) * (y - ybar) for i, y in enumerate(values)) / sxx
    a = ybar - b * xbar
    trend = [a + b * i for i in range(n)]

    period = _SEASON_PERIODS.get(grain)
    idx = {}
    method = "trend"
    dof = n - 2
    if period is not None and n >= 2 * period:
        positions = [_season_pos(d, grain) for d in dates]
        by_pos: dict = {}
        for p, dv in zip(
            positions, (y - t for y, t in zip(values, trend, strict=False)), strict=False
        ):
            by_pos.setdefault(p, []).append(dv)
        raw = {p: sum(v) / len(v) for p, v in by_pos.items()}
        center = sum(raw.values()) / len(raw)
        seasonal_dof = n - 2 - (len(raw) - 1)
        if seasonal_dof >= 3:
            idx = {p: v - center for p, v in raw.items()}
            method = "trend_seasonal"
            dof = seasonal_dof

    fitted = [
        t + (idx.get(_season_pos(d, grain), 0.0) if idx else 0.0)
        for t, d in zip(trend, dates, strict=False)
    ]
    sse = sum((y - f) ** 2 for y, f in zip(values, fitted, strict=False))
    s = math.sqrt(sse / dof) if dof > 0 else 0.0
    t_q = _t_quantile(dof)
    nonneg = min(values) >= 0

    future = _next_buckets(dates[-1], grain, horizon)
    yhat, lower, upper = [], [], []
    for k, fd in enumerate(future, start=1):
        x0 = n - 1 + k
        est = a + b * x0 + (idx.get(_season_pos(fd, grain), 0.0) if idx else 0.0)
        se = s * math.sqrt(1 + 1 / n + (x0 - xbar) ** 2 / sxx)
        lo, hi = est - t_q * se, est + t_q * se
        if nonneg:
            est, lo, hi = max(0.0, est), max(0.0, lo), max(0.0, hi)
        yhat.append(est)
        lower.append(lo)
        upper.append(hi)
    return future, yhat, lower, upper, method


def _as_date(v):
    """Coerce a bucket cell (date/datetime/ISO-ish string) to a date, else None."""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    s = str(v or "")[:10]
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def _resolve_horizon(raw, n):
    if raw == "auto" or raw is None:
        return min(AUTO_HORIZON_CAP, max(3, round(n / 4)))
    try:
        return max(1, min(MAX_HORIZON, int(raw)))
    except (TypeError, ValueError):
        return min(AUTO_HORIZON_CAP, max(3, round(n / 4)))


def _bucket_count(rows, grain):
    """Zero-filled bucket span for `rows`, mirroring compute_forecast's own
    dates construction below. Returns None if the rows can't be parsed into
    an aligned bucket series (caller then just skips the override)."""
    ds = []
    for r in rows:
        d = _as_date(r[0])
        if d is None:
            return None
        ds.append(d)
    if not ds:
        return None
    ds.sort()
    filled: list = []
    d = ds[0]
    last = ds[-1]
    while d <= last:
        if len(filled) > 2000:
            return None
        filled.append(d)
        d = _step(d, grain)
    if filled[-1] != last:
        return None
    return len(filled)


def compute_forecast(definition, columns, rows, visible_rows=None, carry_forward=()):
    """Forecast block for one run result, or {"unavailable": reason}.

    Applies only to the single-date-dimension aggregate shape (D2): exactly
    one column WITH a grain plus >=1 metric. The sparse SQL series is
    zero-filled between its min and max bucket before fitting (GROUP BY
    drops empty buckets; fitting the sparse series would corrupt the trend).
    Never raises on user data.

    `visible_rows`: when `rows` comes from a widened lookback refit (more
    history than what the user actually sees, for fit quality only — #178),
    pass the report's original, un-widened rows here so the auto horizon
    still resolves from what's on screen, not from the wider fit window.
    Omit (or pass the same rows) when there is no widening — the auto
    horizon then resolves from `rows` itself, unchanged from before.

    `carry_forward`: metric indexes (0-based within `metrics`) that are LEVELS
    (a backlog snapshot), not event counts. A missing bucket or NULL cell
    for those repeats the last known value instead of dropping to 0 — a
    weekend nobody measured is not an empty warehouse.
    """
    carry_forward = set(carry_forward or ())
    dims = definition.get("columns") or []
    metrics = definition.get("metrics") or []
    grain = dims[0].get("grain") if len(dims) == 1 and isinstance(dims[0], dict) else None
    if len(dims) != 1 or not grain or not metrics:
        return {"unavailable": "shape"}

    parsed = []
    for r in rows:
        d = _as_date(r[0])
        if d is None:
            return {"unavailable": "bad_buckets"}
        parsed.append((d, r))
    parsed.sort(key=lambda p: p[0])
    if not parsed:
        return {"unavailable": "insufficient_history"}

    metric_start = len(columns) - len(metrics)
    by_bucket = dict(parsed)
    # ponytail: fill min..max of the data only — leading zeros before the
    # first real bucket would fake a longer, flatter history.
    dates: list = []
    d = parsed[0][0]
    last = parsed[-1][0]
    while d <= last:
        if len(dates) > 2000:  # absurd range guard (day grain over years)
            return {"unavailable": "insufficient_history"}
        dates.append(d)
        d = _step(d, grain)
    if dates[-1] != last:  # bucket starts not aligned to the grain steps
        return {"unavailable": "bad_buckets"}

    horizon_n = len(dates)
    if visible_rows is not None:
        visible_n = _bucket_count(visible_rows, grain)
        if visible_n is not None:
            horizon_n = visible_n
    horizon = _resolve_horizon((definition.get("forecast") or {}).get("horizon"), horizon_n)
    # The bucket containing today is still filling up — fitting on it reads a
    # half month as a collapse. Fit on finished buckets only; the projection
    # then starts right after the partial one (which stays on the chart as-is).
    today = datetime.date.today()
    partial_last = len(dates) > MIN_POINTS and dates[-1] <= today < _step(dates[-1], grain)
    fit_n = len(dates) - 1 if partial_last else len(dates)
    series_out, future, method = [], None, None
    for mi in range(len(metrics)):
        values: list = []
        level = mi in carry_forward
        for bucket in dates:
            row = by_bucket.get(bucket)
            cell = row[metric_start + mi] if row is not None else None
            try:
                v = float(cell) if cell is not None else None
            except (TypeError, ValueError):
                v = None
            if v is None:
                v = values[-1] if (level and values) else 0.0
            values.append(v)
        if level:
            # Leading unknowns took 0.0 above — backfill them flat from the
            # first real snapshot so they can't fake a climb from nothing.
            first = next(
                (
                    i
                    for i, bucket in enumerate(dates)
                    if by_bucket.get(bucket) is not None
                    and by_bucket[bucket][metric_start + mi] is not None
                ),
                None,
            )
            if first:
                values[:first] = [values[first]] * first
        fit = forecast_series(dates[:fit_n], values[:fit_n], grain, horizon + int(partial_last))
        if fit is None:
            return {"unavailable": "insufficient_history"}
        future, yhat, lower, upper, method = fit
        if partial_last:  # the first projected bucket IS the partial one — drop it
            future, yhat, lower, upper = future[1:], yhat[1:], lower[1:], upper[1:]
        field = (
            columns[metric_start + mi].get("field")
            if isinstance(columns[metric_start + mi], dict)
            else str(columns[metric_start + mi])
        )
        series_out.append(
            {
                "field": field,
                "values": [round(v, 4) for v in yhat],
                "lower": [round(v, 4) for v in lower],
                "upper": [round(v, 4) for v in upper],
            }
        )
    # metrics is non-empty (guarded above), so the loop ran at least once and
    # future was assigned before any exit past this point.
    assert future is not None
    return {
        "anchor": dates[-1].isoformat(),
        "grain": grain,
        "method": method,
        "horizon": horizon,
        "buckets": [d.isoformat() for d in future],
        "series": series_out,
    }


def forecast_export_rows(columns, rows, forecast, marker_header="Forecast"):
    """(columns2, rows2, forecast_start): actual rows + predicted rows with a
    trailing marker column ('' actual / 'forecast' predicted). The forecast
    rows carry the bucket in the dim cell and yhat in each metric cell;
    bounds are not exported (D7)."""
    cols2 = [*columns, {"field": "__forecast", "header": marker_header}]
    rows2 = [[*r, ""] for r in rows]
    forecast_start = len(rows2)
    metric_start = len(columns) - len(forecast["series"])
    for bi, bucket in enumerate(forecast["buckets"]):
        row = [None] * len(columns)
        row[0] = bucket
        for si, s in enumerate(forecast["series"]):
            row[metric_start + si] = s["values"][bi]
        rows2.append([*row, "forecast"])
    return cols2, rows2, forecast_start
