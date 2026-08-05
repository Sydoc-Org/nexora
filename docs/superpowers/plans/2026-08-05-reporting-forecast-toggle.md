# Reporting: Forecast Toggle on Time-Series Results — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Single-session planning run (recon → draft → self-red-team); **every file path, symbol, and quoted snippet below was Grep/Read-verified against `feature/2.5.65` HEAD (`e5eea54`) on 2026-08-05** — trust the anchors, but re-Grep before editing (this plan quotes code, never line numbers). Plan file: `docs/superpowers/plans/2026-08-05-reporting-forecast-toggle.md`. GitHub issue: **#168**.

**Goal:** Any report result with exactly one date-grained dimension plus metrics gets a "Forecast" toggle: the chart extends past the last bucket with a dashed prediction line and a shaded 95 % confidence band, the table gains clearly-marked predicted rows, exports mark forecast rows, scheduled mails include the forecast only when the saved definition has the toggle on — identically in Simple and Advanced.

**Architecture:** One new pure-stdlib module `nx_lib/reporting/forecast.py` (OLS linear trend + additive seasonal indices per grain, textbook regression prediction intervals — deliberately NOT statsmodels; same no-numpy rule as `nx_lib/reporting/stats.py`). The forecast is computed **server-side on the already-aggregated series**: `POST /api/reporting/run` gains a `forecast` payload block (same bolt-on pattern as the existing `comparison` block), `/api/reporting/export` and the scheduled runner reuse the same `compute_forecast`. The toggle state lives **inside the definition JSON** (`def.forecast = {enabled, horizon}`) so saving/sharing/scheduling inherit it with zero new persistence — no migration, no new permission.

**Tech Stack:** Python stdlib (`math`, `datetime`, `calendar`), Chart.js 4 mixed line-overlay datasets (dashed line + `fill:'-1'` band), matplotlib `fill_between` for scheduled PNGs, pytest unit + integration (`unittest.mock.patch` on `_prepare_run`/`_execute` — the established comparison-test pattern), Playwright e2e with the module's `_stub_run_ok`-style route stubs, Flask-Babel de/fr/it.

---

## Context an engineer needs (read first)

- **Branch/worktree:** this plan was authored in worktree `.claude/worktrees/plan-reporting-forecast-toggle` (branch `plan/reporting-forecast-toggle`, cut from `feature/2.5.65`). Execute there. **Commit per task. Do NOT `git push`, do NOT open a PR** — the owner reviews, merges the worktree branch back into `feature/2.5.65`, and pushes.
- **Parallel sessions are normal** on this repo — the main checkout currently has unrelated uncommitted work (status page #167). Never touch files outside this plan's list; never stash/revert foreign changes.
- **Python for tests:** `C:\dev\nexora\.venv\Scripts\python -m pytest …`. The dev server (`nx -u`) runs global Python — the `.venv` is test-only. No new runtime deps in this plan, so the dual-python trap does not bite here.
- **Anchor on quoted snippets + function names, NEVER line numbers.** Re-`Grep` a snippet if it has moved.
- **TDD is the house rule.** Backend tasks are strict RED→GREEN. Frontend tasks write the failing Playwright e2e first.
- **TEST env has NO Statistics DB** — a docprocessing/table run can never execute in e2e. Backend integration tests patch `nx_lib.views.reporting._prepare_run` and `_execute` (copy the pattern of `test_run_compare_true_with_token_filter_returns_comparison` in `tests/integration/test_reporting_routes.py`); e2e stubs `**/api/reporting/run` (see `_stub_run_ok` in `tests/e2e/test_reporting_simple.py`).
- **Before running any e2e tier:** `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py` (stale NEXORA_TEST state fails order-dependent e2e tests).
- **Jinja template cache is process-lifetime** — restart the dev server (`nx -r`) before ANY manual browser check.
- **e2e locale is English** — assert English strings.
- **Migrations needed: NO.** The toggle rides inside `DefinitionJSON`; `dbo.Reports` is untouched. No new permission (`reporting.view` gates the run; the block only appears when the definition asks for it). **No `deploy.yml` changes** (only `nx_lib/`, `templates/`, `static/`, `ops/`, `tests/`, `translations/`, `docs/` touched — all already deployed or excluded).
- **i18n: ONE late pybabel cycle (Task 10).** New msgids land in Tasks 5–8; `tests/unit/test_translations.py` is expected RED in between — use `--deselect tests/unit/test_translations.py` for the fast tier until Task 10. `tests/unit/test_reporting_i18n_lint.py` also lints the reporting partials — new UI strings must be `{{ _('…') }}`-wrapped from the start.
- **PROD URL prefix:** the Simple pane's `api()` helper already normalizes through `API_PREFIX`; do not hand-build URLs.
- **Visual contract:** never rename a `.reporting-*` class; preserve every `data-testid`/`id`; `.nx-rise*` animations use fill-mode `backwards`, never `both`.
- **gitlint:** conventional-commit title ≤72 chars, imperative, no trailing period; non-empty body wrapped ≤100 chars; commit via Bash `git commit -F - <<'EOF' … EOF`. If `ruff-format` rewrites a file the first attempt fails — `git add -u` and recommit. If INT is unreachable: `SQL_SYNC_SKIP=1`, never `--no-verify`.
- **Commit trailer names the EXECUTING model** — the blocks below say `Claude Opus 5`; substitute the real executor if different.

---

## Decisions locked in

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Pure-stdlib engine** (`forecast.py`): OLS linear trend + additive seasonal indices (classical decomposition), residual-based 95 % prediction interval with t-quantile and horizon widening. No statsmodels/numpy/pandas. | Owner-approved 2026-08-05. `stats.py` already codifies the no-heavy-deps rule for this WSGI app; the series here are weeks–months long — SARIMA gains nothing. The engine hides behind `compute_forecast`'s contract, so statsmodels can be swapped in later as one file change. |
| D2 | **Single-dimension only** (owner-approved): forecast requires exactly 1 column WITH a grain + ≥1 metric. 2+ dims grey the toggle with a tooltip; 0 dims (stat card) have no toggle. | Per-series forecasting over up to 12 series triples the surface and 12 overlapping bands are unreadable. Mirrors `zeroFillDateBuckets`'s own dims≥2 ponytail precedent. |
| D3 | **Seasonal period by grain:** day→7 (weekday), month→12 (calendar month), quarter→4; week/year → trend-only. Seasonal fit needs `n ≥ 2·period` and `dof ≥ 3`; else trend-only needs `n ≥ 5` (`MIN_POINTS`); else `{"unavailable": …}`. | Season positions come from the calendar (weekday/month/quarter of the bucket date), not `i mod period`, so gaps and partial periods can't shift the cycle. |
| D4 | **Toggle + horizon persist in the definition:** `def.forecast = {"enabled": true, "horizon": "auto"\|int}`. `validate_report_definition` gains an explicit whitelist check for the block. Horizon `auto` = `max(3, round(n/4))` capped 30; explicit int clamped 1–60. UI offers Auto / +7 / +14 / +30 buckets. | Definitions already carry `chartType` the same way; saved reports, shares, and schedules inherit the toggle for free — which is exactly what the issue demands for scheduled mails. |
| D5 | **Server computes on the aggregated result** inside `api_run` (same spot as the `comparison` block), after **server-side zero-fill** of missing buckets between the series' min and max bucket. Response block: `{"anchor", "grain", "method", "horizon", "buckets": [iso…], "series": [{"field", "values", "lower", "upper"}]}` or `{"unavailable": "<reason>"}`. | Sparse `GROUP BY` drops empty buckets — fitting on the sparse series would corrupt the trend. The client's own `zeroFillDateBuckets` fills only for display; the server must fill for the fit. `anchor` (last history bucket) lets the client keep its display zero-fill from colliding with forecast buckets. |
| D6 | **Chart rendering:** dashed accent line per metric (bridged from the last actual point), shaded band **only when exactly 1 metric**; band/forecast datasets are excluded from legend + drill. Forecast drawn only for line/bar (incl. the bar case as a line overlay); pie/doughnut unchanged. | One band is information, twelve are noise. Chart.js mixed types make the bar+line overlay free. |
| D7 | **Table + export marking:** predicted rows appended after actuals with an italic/grey style and a "Forecast" badge (web) resp. a trailing "Forecast" marker column (`""` for actuals, `"forecast"` for predictions) in xlsx/csv, xlsx additionally grey-italic via a new optional `forecast_start` arg to `rows_to_xlsx`. Bounds are NOT exported (v1). | "Never exported as if they were actuals" — a marker column survives every downstream tool; styling alone doesn't survive CSV. |
| D8 | **Drill-through excluded** on predicted points/rows: chart clicks with `index >= forecastStart` (or on a forecast/band dataset) are ignored; forecast table rows get no drill handler. | Predicted points have no underlying rows (issue requirement). |
| D9 | **Scheduled mails:** `ops/run_scheduled_reports.py` computes the forecast itself (definition toggle on → `compute_forecast`), passes it to `render_chart_png(forecast=…)` and appends the marker rows to the attachment. `runner.execute_definition`'s signature stays untouched. The runner's table-provider validate call also gains the missing `grainable_fields` argument (latent bug: a saved table-source definition WITH a grain — e.g. any Backlog History over-time report — bounces validation in the scheduler today). | Alert totals (`total_definition`) strip columns, so alerts never see a forecast — correct. |
| D10 | **KPI band, stat card, preview cache, drill drawer, AI captions all read actuals only** — the forecast block is kept separate from `rows` end-to-end and only merged at the final render/export surfaces. | One merge point per surface; no risk of a forecast value polluting a KPI delta. |

---

## Owner actions (not for the executor)

1. **Review + merge** `plan/reporting-forecast-toggle` back into `feature/2.5.65`, then push (this session is commit-only). Close #168 with the fix SHA after merge.
2. **Band-per-series** (multi-metric bands), **exported bounds columns**, and **forecast in the AI assistant's vocabulary** were deliberately deferred — say the word if wanted.

---

# PHASE 1 — Backend engine

### Task 1: `forecast.py` core — `forecast_series` (fit + prediction interval)

**Files:**
- Create: `nx_lib/reporting/forecast.py`
- Create: `tests/unit/test_reporting_forecast.py`

**Interfaces:**
- Produces: `forecast_series(dates, values, grain, horizon)` → `(future_dates, yhat, lower, upper, method)` or `None` (too little history / degenerate). `dates`: contiguous `datetime.date` bucket starts; `values`: floats; `method`: `"trend_seasonal"` or `"trend"`. Also `_next_buckets(last, grain, n)` and `_season_pos(d, grain)` used by Task 2. Constant `MIN_POINTS = 5`.

- [ ] **Step 1 — Write the failing tests** (`tests/unit/test_reporting_forecast.py`):

```python
"""Unit tests for nx_lib.reporting.forecast — pure math, no DB/Flask."""

import datetime

from nx_lib.reporting.forecast import MIN_POINTS, _next_buckets, forecast_series


def _days(n, start="2026-06-01"):
    d0 = datetime.date.fromisoformat(start)
    return [d0 + datetime.timedelta(days=i) for i in range(n)]


def _months(n, start="2025-01-01"):
    d0 = datetime.date.fromisoformat(start)
    out = []
    for i in range(n):
        total = d0.year * 12 + (d0.month - 1) + i
        out.append(datetime.date(total // 12, total % 12 + 1, 1))
    return out


def test_pure_trend_is_recovered():
    # y = 10 + 2x over 8 monthly buckets -> next points continue exactly.
    dates = _months(8)
    values = [10 + 2 * i for i in range(8)]
    future, yhat, lower, upper, method = forecast_series(dates, values, "month", 3)
    assert method == "trend"  # 8 < 2*12: seasonal not attempted for month grain
    assert [round(v, 6) for v in yhat] == [26, 28, 30]
    assert future[0] == datetime.date(2025, 9, 1)
    # zero residuals -> zero-width band
    assert all(round(lo, 6) == round(y, 6) for lo, y in zip(lower, yhat))


def test_weekday_seasonality_is_recovered():
    # 4 full weeks of a flat series with a weekend dip; day grain, period 7.
    dates = _days(28)
    values = [(2.0 if d.weekday() >= 5 else 10.0) for d in dates]
    future, yhat, lower, upper, method = forecast_series(dates, values, "day", 7)
    assert method == "trend_seasonal"
    by_wd = dict(zip([d.weekday() for d in future], yhat))
    assert by_wd[5] < 5 < by_wd[0]  # Saturday predicted low, Monday high


def test_band_widens_with_horizon():
    dates = _months(12)
    values = [10, 13, 11, 15, 12, 16, 13, 18, 14, 19, 16, 20]  # noisy up-trend
    _, yhat, lower, upper, _ = forecast_series(dates, values, "month", 4)
    w = [u - lo for u, lo in zip(upper, lower)]
    assert w[0] > 0 and w[-1] > w[0]


def test_nonnegative_series_clamps_lower_at_zero():
    dates = _months(6)
    values = [5, 4, 3, 2, 1, 0]  # steep down-trend crosses zero
    _, yhat, lower, _, _ = forecast_series(dates, values, "month", 4)
    assert all(lo >= 0 for lo in lower)
    assert all(y >= 0 for y in yhat)


def test_too_little_history_returns_none():
    dates = _months(MIN_POINTS - 1)
    assert forecast_series(dates, [1.0] * len(dates), "month", 3) is None


def test_next_buckets_week_and_quarter():
    assert _next_buckets(datetime.date(2026, 8, 3), "week", 2) == [
        datetime.date(2026, 8, 10),
        datetime.date(2026, 8, 17),
    ]
    assert _next_buckets(datetime.date(2026, 10, 1), "quarter", 2) == [
        datetime.date(2027, 1, 1),
        datetime.date(2027, 4, 1),
    ]
```

- [ ] **Step 2 — Run, expect RED** (module missing):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_forecast.py -q`
Expected: FAIL — `ModuleNotFoundError: nx_lib.reporting.forecast`.

- [ ] **Step 3 — Implement** `nx_lib/reporting/forecast.py`:

```python
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
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
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
        by_pos = {}
        for p, dv in zip(positions, (y - t for y, t in zip(values, trend))):
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
        for t, d in zip(trend, dates)
    ]
    sse = sum((y - f) ** 2 for y, f in zip(values, fitted))
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
```

- [ ] **Step 4 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_forecast.py -q`
Expected: PASS.

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/reporting/forecast.py tests/unit/test_reporting_forecast.py
git commit -F - <<'EOF'
feat(reporting): stdlib forecast engine - trend, seasonality, intervals

OLS linear trend plus additive seasonal indices (day->7, month->12,
quarter->4; week/year trend-only) with 95% regression prediction
intervals (t-quantile, horizon widening, zero clamp for nonnegative
series). Pure stdlib by design - same no-numpy rule as stats.py; the
engine hides behind the compute_forecast contract (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 2: `compute_forecast` — definition gate, zero-fill, response block

**Files:**
- Modify: `nx_lib/reporting/forecast.py` (append)
- Test: `tests/unit/test_reporting_forecast.py` (append)

**Interfaces:**
- Produces: `compute_forecast(definition, columns, rows)` → response-block dict — either `{"anchor": iso, "grain": str, "method": str, "horizon": int, "buckets": [iso…], "series": [{"field": str, "values": […], "lower": […], "upper": […]}]}` (series in metric order, floats rounded to 4 decimals) or `{"unavailable": "<machine-readable reason>"}` (reasons: `"shape"`, `"bad_buckets"`, `"insufficient_history"`). Also `forecast_export_rows(columns, rows, forecast, marker_header="Forecast")` → `(columns2, rows2, forecast_start)` for Tasks 8–9. Never raises on user data; horizon read from `definition["forecast"]["horizon"]`.

- [ ] **Step 1 — Append the failing tests:**

```python
from nx_lib.reporting.forecast import compute_forecast, forecast_export_rows


def _definition(horizon="auto"):
    return {
        "source": "backlog_history",
        "columns": [{"field": "SnapshotAt", "grain": "month"}],
        "metrics": [{"metric": "backlog_total"}],
        "forecast": {"enabled": True, "horizon": horizon},
    }


_COLS = [{"field": "SnapshotAt"}, {"field": "backlog_total"}]


def _rows(n=8):
    return [[f"{2025 + (i // 12):04d}-{i % 12 + 1:02d}-01", 10 + 2 * i] for i in range(n)]


def test_compute_forecast_happy_path():
    fc = compute_forecast(_definition(horizon=3), _COLS, _rows())
    assert "unavailable" not in fc
    assert fc["grain"] == "month" and fc["horizon"] == 3
    assert fc["anchor"] == "2025-08-01"
    assert fc["buckets"] == ["2025-09-01", "2025-10-01", "2025-11-01"]
    assert fc["series"][0]["field"] == "backlog_total"
    assert [round(v) for v in fc["series"][0]["values"]] == [26, 28, 30]


def test_compute_forecast_zero_fills_missing_buckets():
    rows = _rows(8)
    del rows[3]  # a month with no snapshot rows at all
    fc = compute_forecast(_definition(horizon=2), _COLS, rows)
    assert "unavailable" not in fc
    # the gap was filled with 0, so the fit saw 8 contiguous buckets
    assert fc["anchor"] == "2025-08-01"


def test_compute_forecast_auto_horizon_scales_with_history():
    fc = compute_forecast(_definition(), _COLS, _rows(16))
    assert fc["horizon"] == 4  # max(3, round(16/4))


def test_compute_forecast_rejects_wrong_shape():
    two_dims = _definition()
    two_dims["columns"].append({"field": "ProcessName"})
    assert compute_forecast(two_dims, _COLS, _rows())["unavailable"] == "shape"
    no_grain = _definition()
    del no_grain["columns"][0]["grain"]
    assert compute_forecast(no_grain, _COLS, _rows())["unavailable"] == "shape"


def test_compute_forecast_insufficient_history():
    assert (
        compute_forecast(_definition(), _COLS, _rows(3))["unavailable"]
        == "insufficient_history"
    )


def test_forecast_export_rows_marks_predictions():
    fc = compute_forecast(_definition(horizon=2), _COLS, _rows())
    cols2, rows2, start = forecast_export_rows(_COLS, _rows(), fc)
    assert cols2[-1] == {"field": "__forecast", "header": "Forecast"}
    assert start == 8 and len(rows2) == 10
    assert rows2[0][-1] == "" and rows2[-1][-1] == "forecast"
    assert rows2[8][0] == "2025-09-01" and round(rows2[8][1]) == 26
```

- [ ] **Step 2 — Run, expect RED** (`ImportError: compute_forecast`):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_forecast.py -q`

- [ ] **Step 3 — Append the implementation** to `nx_lib/reporting/forecast.py`:

```python
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


def compute_forecast(definition, columns, rows):
    """Forecast block for one run result, or {"unavailable": reason}.

    Applies only to the single-date-dimension aggregate shape (D2): exactly
    one column WITH a grain plus >=1 metric. The sparse SQL series is
    zero-filled between its min and max bucket before fitting (GROUP BY
    drops empty buckets; fitting the sparse series would corrupt the trend).
    Never raises on user data.
    """
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
    by_bucket = {d: r for d, r in parsed}
    # ponytail: fill min..max of the data only — leading zeros before the
    # first real bucket would fake a longer, flatter history.
    dates, d = [], parsed[0][0]
    last = parsed[-1][0]
    while d <= last:
        if len(dates) > 2000:  # absurd range guard (day grain over years)
            return {"unavailable": "insufficient_history"}
        dates.append(d)
        d = _step(d, grain)
    if dates[-1] != last:  # bucket starts not aligned to the grain steps
        return {"unavailable": "bad_buckets"}

    horizon = _resolve_horizon((definition.get("forecast") or {}).get("horizon"), len(dates))
    series_out, future, method = [], None, None
    for mi in range(len(metrics)):
        values = []
        for bucket in dates:
            row = by_bucket.get(bucket)
            cell = row[metric_start + mi] if row is not None else 0
            try:
                values.append(float(cell if cell is not None else 0))
            except (TypeError, ValueError):
                values.append(0.0)
        fit = forecast_series(dates, values, grain, horizon)
        if fit is None:
            return {"unavailable": "insufficient_history"}
        future, yhat, lower, upper, method = fit
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
    cols2 = list(columns) + [{"field": "__forecast", "header": marker_header}]
    rows2 = [list(r) + [""] for r in rows]
    forecast_start = len(rows2)
    metric_start = len(columns) - len(forecast["series"])
    for bi, bucket in enumerate(forecast["buckets"]):
        row = [None] * len(columns)
        row[0] = bucket
        for si, s in enumerate(forecast["series"]):
            row[metric_start + si] = s["values"][bi]
        rows2.append(row + ["forecast"])
    return cols2, rows2, forecast_start
```

- [ ] **Step 4 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_forecast.py -q`

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/reporting/forecast.py tests/unit/test_reporting_forecast.py
git commit -F - <<'EOF'
feat(reporting): compute_forecast - definition gate, zero-fill, block

compute_forecast validates the single-date-dim + metrics shape,
zero-fills the sparse SQL series between its min and max bucket, fits
every metric and returns the response block (anchor/buckets/series) or
{"unavailable": reason}. forecast_export_rows appends marker-column
prediction rows for the export surfaces (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 3: schema validation for the `forecast` definition block

**Files:**
- Modify: `nx_lib/reporting/schema.py`
- Test: `tests/unit/test_reporting_schema.py` (append)

**Interfaces:**
- Produces: `validate_report_definition` accepts an optional `forecast` key: dict with only `enabled` (bool) and `horizon` (`"auto"` or int 1–60); anything else raises `ReportDefinitionError`. Definitions without the key are untouched (back-compat with every saved report).

- [ ] **Step 1 — Write the failing tests.** Append to `tests/unit/test_reporting_schema.py`. The file already invokes the validator directly as `validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)` (Grep that exact call) and builds `d` from a module-level valid-definition dict — copy the neighbouring tests' `d = …` construction and the module constants verbatim, then:

```python
def test_forecast_block_valid_shapes_accepted():
    d = _valid()  # copy: however the neighbouring tests build their valid definition
    d["forecast"] = {"enabled": True, "horizon": "auto"}
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)
    d["forecast"] = {"enabled": False, "horizon": 12}
    validate_report_definition(d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000)


def test_forecast_block_bad_shapes_rejected():
    for bad in (
        "yes",                                   # not an object
        {"enabled": "true"},                     # non-bool enabled
        {"enabled": True, "horizon": 0},         # below range
        {"enabled": True, "horizon": 61},        # above range
        {"enabled": True, "horizon": True},      # bool masquerading as int
        {"enabled": True, "surprise": 1},        # unknown key
    ):
        d = _valid()
        d["forecast"] = bad
        with pytest.raises(ReportDefinitionError):
            validate_report_definition(
                d, CATALOG_FIELDS, FILTERABLE, SORTABLE, max_row_limit=50000
            )
```

> `_valid()` is the one stand-in — the file's constants `CATALOG_FIELDS`/`FILTERABLE`/`SORTABLE`, `pytest`, and `ReportDefinitionError` are already imported at its top (verified). If the grain-carrying variant needs `grainable_fields`, mirror the kwargs of the file's existing grain tests.

- [ ] **Step 2 — Run, expect RED** (bad shapes currently pass — unknown keys are ignored):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_schema.py -k forecast -q`

- [ ] **Step 3 — Implement.** In `nx_lib/reporting/schema.py`, inside `validate_report_definition`, directly before the anchor `row_limit = rd.get("rowLimit")`:

```python
    forecast = rd.get("forecast")
    if forecast is not None:
        if not isinstance(forecast, dict):
            raise ReportDefinitionError("forecast must be an object")
        extra = set(forecast) - {"enabled", "horizon"}
        if extra:
            raise ReportDefinitionError(f"unexpected keys in forecast: {sorted(extra)}")
        if not isinstance(forecast.get("enabled", False), bool):
            raise ReportDefinitionError("forecast.enabled must be a boolean")
        horizon = forecast.get("horizon", "auto")
        if horizon != "auto" and (
            isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 60
        ):
            raise ReportDefinitionError("forecast.horizon must be 'auto' or an int in [1, 60]")
```

- [ ] **Step 4 — Run, expect GREEN** (plus the untouched schema tests):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_schema.py -q`

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/reporting/schema.py tests/unit/test_reporting_schema.py
git commit -F - <<'EOF'
feat(reporting): validate the forecast block in report definitions

Optional definition key forecast={enabled: bool, horizon: "auto"|1..60},
whitelist-checked like every other definition field; absent key stays a
no-op so all existing saved reports validate unchanged (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 4: `/api/reporting/run` — forecast payload block

**Files:**
- Modify: `nx_lib/views/reporting.py` (`api_run` + one import)
- Test: `tests/integration/test_reporting_routes.py` (append)

**Interfaces:**
- Consumes: Task 2's `compute_forecast`.
- Produces: when the posted definition has `forecast.enabled: true`, the run payload gains `payload["forecast"]` = the compute_forecast block (incl. the `unavailable` shape). Any forecast exception degrades to a logged warning, never a 500 — mirroring the `comparison` block's failure policy.

- [ ] **Step 1 — Write the failing integration tests.** Append to `tests/integration/test_reporting_routes.py`, copying the patch pattern of the neighbouring `test_run_compare_true_with_token_filter_returns_comparison` (anchor: `patch("nx_lib.views.reporting._execute", side_effect=[main_rows, comparison_rows])` — same `admin_client` fixture, same `patch("nx_lib.views.reporting._prepare_run", …)` style):

```python
# --- forecast: definition toggle (issue #168) ---

_FC_DEF = {
    "schemaVersion": 1,
    "visualization": "table",
    "source": "docprocessing",
    "title": "Backlog over time",
    "columns": [{"field": "export_date", "grain": "month"}],
    "metrics": [{"metric": "doc_count"}],
    "filters": [],
    "sort": [],
    "scope": {"clients": [], "processes": []},
    "rowLimit": 5000,
    "forecast": {"enabled": True, "horizon": 3},
}

_FC_COLS = [{"field": "export_date"}, {"field": "doc_count"}]
_FC_ROWS = [[f"2025-{m:02d}-01", 10 + 2 * (m - 1)] for m in range(1, 9)]


def test_run_forecast_enabled_returns_block(admin_client):
    with (
        patch(
            "nx_lib.views.reporting._prepare_run",
            return_value=(_FC_COLS, "SELECT 1", [], None),
        ),
        patch("nx_lib.views.reporting._execute", return_value=_FC_ROWS),
    ):
        resp = admin_client.post("/api/reporting/run", json=_FC_DEF)
    assert resp.status_code == 200
    fc = resp.get_json().get("forecast")
    assert fc and "unavailable" not in fc
    assert fc["horizon"] == 3 and len(fc["buckets"]) == 3
    assert fc["series"][0]["field"] == "doc_count"
    assert len(fc["series"][0]["values"]) == 3
    assert fc["series"][0]["lower"][0] <= fc["series"][0]["values"][0] <= fc["series"][0]["upper"][0]


def test_run_forecast_disabled_or_absent_omits_block(admin_client):
    quiet = dict(_FC_DEF, forecast={"enabled": False, "horizon": 3})
    with (
        patch(
            "nx_lib.views.reporting._prepare_run",
            return_value=(_FC_COLS, "SELECT 1", [], None),
        ),
        patch("nx_lib.views.reporting._execute", return_value=_FC_ROWS),
    ):
        resp = admin_client.post("/api/reporting/run", json=quiet)
    assert resp.status_code == 200
    assert "forecast" not in resp.get_json()


def test_run_forecast_short_history_reports_unavailable(admin_client):
    with (
        patch(
            "nx_lib.views.reporting._prepare_run",
            return_value=(_FC_COLS, "SELECT 1", [], None),
        ),
        patch("nx_lib.views.reporting._execute", return_value=_FC_ROWS[:3]),
    ):
        resp = admin_client.post("/api/reporting/run", json=_FC_DEF)
    assert resp.status_code == 200
    assert resp.get_json()["forecast"]["unavailable"] == "insufficient_history"
```

- [ ] **Step 2 — Run, expect RED:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -k forecast -q`
Expected: FAIL (`forecast` key absent).

- [ ] **Step 3 — Implement.** In `nx_lib/views/reporting.py`:

(a) extend the reporting-module import block (anchor: the existing `from ..reporting.schema import (` / neighbouring `from ..reporting.…` imports at the top of the file — match their style):

```python
from ..reporting.forecast import compute_forecast, forecast_export_rows
```

(`forecast_export_rows` is used by Task 8 — importing both now avoids touching the import twice.)

(b) in `api_run`, directly after the `if rd.get("compare"):` block ends (anchor: the line `current_app.logger.warning(f"/api/reporting/run comparison skipped: {e}")` and its closing indentation, right before the comment starting `# rd is the original request body (tokens intact)`):

```python
    fc_req = rd.get("forecast")
    if isinstance(fc_req, dict) and fc_req.get("enabled"):
        try:
            payload["forecast"] = compute_forecast(rd, columns, rows)
        except Exception as e:  # a forecast must never take down the run
            current_app.logger.warning(f"/api/reporting/run forecast skipped: {e}")
```

- [ ] **Step 4 — Run, expect GREEN** (whole integration file — the new import must not break anything):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/integration/test_reporting_routes.py -q`

- [ ] **Step 5 — Commit:**

```bash
git add nx_lib/views/reporting.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): forecast block in the /api/reporting/run payload

When the posted definition carries forecast.enabled, the run response
gains a forecast block (buckets, per-metric values and 95% bounds, or an
unavailable reason) computed server-side on the aggregated rows - same
bolt-on pattern and failure policy as the comparison block (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 2 — Simple tab

### Task 5: Simple — toggle + horizon UI, chart dashed line + band

**Files:**
- Modify: `templates/_reporting_simple.html` (toggle + horizon in the chart toolbar)
- Modify: `templates/js/_reporting_simple_js.html` (toggle wiring, chart forecast rendering)
- Modify: `static/css/reporting.css` (append-only)
- Test: `tests/e2e/test_reporting_simple.py` (append)

**Interfaces:**
- Consumes: Task 4's payload block.
- Produces: `#rsForecastToggle` (`data-testid="rs-forecast-toggle"`, `aria-pressed`) + `#rsForecastHorizon` (`data-testid="rs-forecast-horizon"`, options auto/7/14/30) inside `#rsChartTools`. Toggling writes `state.current.def.forecast = {enabled, horizon}` (delete on off) and re-runs. Chart: dashed accent line per metric bridged from the last actual point; shaded band when exactly 1 metric; forecast/band datasets excluded from legend, tooltip unchanged; `state.chartData.forecastStart` = history length (Task 6's drill guard reads it). Chart note shows the forecast disclaimer when active, or the not-enough-history message on `unavailable`.

- [ ] **Step 1 — Write the failing e2e test.** Append to `tests/e2e/test_reporting_simple.py`, reusing `_login` and the module's stub helpers (Grep `def _stub_run_ok(page, capture=None)` — this test needs its own run stub so it can branch on the posted body):

```python
def test_forecast_toggle_requests_and_renders_forecast(nexora_server, page):
    """Toggling Forecast re-runs with forecast.enabled and renders the
    dashed-extension buckets as marked table rows."""
    _stub_catalog(page)  # copy the source/metrics/library stub set used by the
                         # neighbouring wizard tests in this file, verbatim
    fc_block = {
        "anchor": "2025-08-01", "grain": "month", "method": "trend",
        "horizon": 3, "buckets": ["2025-09-01", "2025-10-01", "2025-11-01"],
        "series": [{"field": "doc_count",
                    "values": [26.0, 28.0, 30.0],
                    "lower": [24.0, 25.5, 27.0],
                    "upper": [28.0, 30.5, 33.0]}],
    }
    def run_stub(route):
        body = route.request.post_data_json or {}
        payload = {
            "columns": [{"field": "export_date"}, {"field": "doc_count"}],
            "rows": [[f"2025-{m:02d}-01", 10 + 2 * (m - 1)] for m in range(1, 9)],
            "rowCount": 8, "truncated": False, "resolvedDates": [],
        }
        if (body.get("forecast") or {}).get("enabled"):
            payload["forecast"] = fc_block
        route.fulfill(json=payload)
    page.route("**/api/reporting/run", run_stub)
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    # Build/run a 1-date-dim + metric report the same way the neighbouring
    # wizard e2e tests do (copy their click sequence), then:
    toggle = page.get_by_test_id("rs-forecast-toggle")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_test_id("rs-forecast-horizon")).to_be_visible()
    # Predicted rows land in the table, marked
    page.get_by_test_id("rs-table-toggle").click()
    rows = page.get_by_test_id("rs-forecast-row")
    expect(rows).to_have_count(3)
    expect(rows.first).to_contain_text("2025-09-01")
    expect(rows.first).to_contain_text("Forecast")
    # Toggle off -> rows disappear
    toggle.click()
    expect(page.get_by_test_id("rs-forecast-row")).to_have_count(0)
```

> The catalog/wizard stub helpers and the exact wizard click sequence MUST be copied from the neighbouring tests in the same file at execution time — do not invent them. If `rs-table-toggle` is not the table toggle's testid, Grep `rsTableToggle` in `templates/_reporting_simple.html` for the real one.

- [ ] **Step 2 — Run, expect RED** (`rs-forecast-toggle` not found):

Run: `C:\dev\nexora\.venv\Scripts\python scripts\test_db_reset.py; C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k forecast_toggle -q`

- [ ] **Step 3 — Toolbar markup.** In `templates/_reporting_simple.html`, inside `#rsChartTools`, directly after the `rsChartPng` button (anchor: `<button type="button" class="reporting-chartbtn" id="rsChartPng"`… line), add:

```html
          <button type="button" class="reporting-chartbtn" id="rsForecastToggle" aria-pressed="false" title="{{ _('Forecast') }}" aria-label="{{ _('Forecast') }}" data-testid="rs-forecast-toggle"><i class="fas fa-arrow-trend-up" aria-hidden="true"></i></button>
          <select id="rsForecastHorizon" class="rs-forecast-horizon" hidden aria-label="{{ _('Forecast horizon') }}" data-testid="rs-forecast-horizon">
            <option value="auto">{{ _('Auto') }}</option>
            <option value="7">+7</option>
            <option value="14">+14</option>
            <option value="30">+30</option>
          </select>
```

- [ ] **Step 4 — JS wiring.** In `templates/js/_reporting_simple_js.html`:

(a) I18N keys — anchor: the `var I18N = {` map near the top; add (matching the file's `{{ _("…")|tojson }}` idiom):

```js
    forecastLabel: {{ _("Forecast")|tojson }},
    forecastNote: {{ _("Dotted line and shaded band are forecast values, not actuals.")|tojson }},
    forecastUnavailable: {{ _("Not enough history to forecast this series.")|tojson }},
    forecastNeedsShape: {{ _("Forecast requires one date breakdown with a metric.")|tojson }},
```

(b) Toggle + horizon handlers — add near the existing `el('rsChartTools').addEventListener('click', …)` block (anchor: `state.current.def.chartType = btn.dataset.type;`):

```js
  function forecastEligible(def) {
    var cols = (def && def.columns) || [];
    return cols.length === 1 && !!cols[0].grain &&
      Array.isArray(def.metrics) && def.metrics.length > 0;
  }
  function syncForecastCtl(def, forecast) {
    var btn = el('rsForecastToggle'), sel = el('rsForecastHorizon');
    if (!btn) return;
    var eligible = forecastEligible(def);
    var on = eligible && !!(def.forecast && def.forecast.enabled);
    btn.disabled = !eligible;
    btn.title = eligible ? I18N.forecastLabel : I18N.forecastNeedsShape;
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.classList.toggle('is-selected', on);
    sel.hidden = !on;
    if (on && def.forecast.horizon) sel.value = String(def.forecast.horizon);
    if (on && forecast && forecast.unavailable) {
      el('rsChartNote').textContent = I18N.forecastUnavailable;
      el('rsChartNote').hidden = false;
    } else if (on) {
      el('rsChartNote').textContent = I18N.forecastNote;
      el('rsChartNote').hidden = false;
    }
  }
  el('rsForecastToggle').addEventListener('click', function () {
    var cur = state.current;
    if (!cur || !cur.def || this.disabled) return;
    if (cur.def.forecast && cur.def.forecast.enabled) {
      delete cur.def.forecast;
    } else {
      var h = el('rsForecastHorizon').value;
      cur.def.forecast = { enabled: true, horizon: h === 'auto' ? 'auto' : parseInt(h, 10) };
    }
    runCurrent();
  });
  el('rsForecastHorizon').addEventListener('change', function () {
    var cur = state.current;
    if (!cur || !cur.def || !cur.def.forecast) return;
    var h = this.value;
    cur.def.forecast.horizon = h === 'auto' ? 'auto' : parseInt(h, 10);
    runCurrent();
  });
```

> If the enclosing function scope makes `runCurrent` unreachable from there, place the two listeners beside the existing `el('rsChartTools').addEventListener` (same scope as `renderChart`) — Grep `runCurrent` call sites first.

(c) Grand-total clone must not forecast — anchor `var totalDef = JSON.parse(JSON.stringify(def));` … after `totalDef.sort = [];` add:

```js
      delete totalDef.forecast;
```

(d) Thread the block through the run path — anchor `var charted = (hasMetrics && dims) ? !!mountChart(def, columns, rows) : false;`; replace with:

```js
    var charted = (hasMetrics && dims)
      ? !!mountChart(def, columns, rows, res.data.forecast || null) : false;
    syncForecastCtl(def, res.data.forecast || null);
```

(e) `mountChart` — change the signature `function mountChart(def, columns, rows) {` to `function mountChart(def, columns, rows, forecast) {`. In the **single-dim branch** (anchor: `state.chartData = {\n      labels: labels, rawX: rawX, datasets: datasets, multiSeries: false,`), directly before that assignment add:

```js
    var fc = (forecast && !forecast.unavailable &&
              (forecast.buckets || []).length) ? forecast : null;
    var histN = labels.length;
    if (fc) {
      labels = labels.concat(fc.buckets.map(function (b) { return String(b).slice(0, 10); }));
    }
```

and extend the assignment with the two new keys:

```js
    state.chartData = {
      labels: labels, rawX: rawX, datasets: datasets, multiSeries: false,
      forecast: fc, forecastStart: histN,
      type: def.chartType || (isDate ? 'line' : 'bar')
    };
```

(The dims≥2 branch ignores `forecast` — D2.)

(f) `renderChart` — inside `function renderChart(type) {`, after the existing `var datasets = d.datasets.map(function (ds) {…});` block and before the `allInts` computation, add:

```js
    var fcActive = !!(d.forecast && !multi && (chartJsType === 'line' || chartJsType === 'bar'));
    if (fcActive) {
      var fc = d.forecast;
      var histN = d.forecastStart;
      var pad = fc.buckets.map(function () { return null; });
      datasets = datasets.map(function (ds) {
        return Object.assign({}, ds, { data: ds.data.concat(pad) });
      });
      var fcAccent = isDark ? '#818cf8' : '#4f46e5';
      var lead = [];
      for (var li = 0; li < histN - 1; li++) lead.push(null);
      fc.series.forEach(function (s, si) {
        var base = d.datasets[si];
        var bridge = base ? base.data[histN - 1] : null;
        datasets.push({
          label: (base ? base.label : s.field) + ' · ' + I18N.forecastLabel,
          data: lead.concat([bridge], s.values),
          type: 'line', borderColor: fcAccent, borderDash: [6, 4],
          borderWidth: 2, backgroundColor: 'transparent',
          pointStyle: 'rectRot', fill: false, tension: .25, _forecast: true
        });
      });
      if (fc.series.length === 1) {
        var s0 = fc.series[0];
        var b0 = d.datasets[0] ? d.datasets[0].data[histN - 1] : null;
        var bandFill = isDark ? 'rgba(129,140,248,.18)' : 'rgba(79,70,229,.12)';
        datasets.push({ label: '', data: lead.concat([b0], s0.upper), type: 'line',
          borderWidth: 0, pointRadius: 0, backgroundColor: 'transparent',
          fill: false, _band: true });
        datasets.push({ label: '', data: lead.concat([b0], s0.lower), type: 'line',
          borderWidth: 0, pointRadius: 0, backgroundColor: bandFill,
          fill: '-1', _band: true });
      }
    }
```

Then two option tweaks inside the same `new Chart(…)` call:
- legend: anchor `plugins: { legend: { display: multi || circular || (d.datasets && d.datasets.length > 1) },` → add a labels filter so band datasets never appear:

```js
                 plugins: { legend: { display: multi || circular || (d.datasets && d.datasets.length > 1) || fcActive,
                                      labels: { filter: function (item, data) {
                                        return !(data.datasets[item.datasetIndex] || {})._band;
                                      } } },
```

- drill guard in `onClick` (anchor `if (els.length) drillFromChart(els[0].index, els[0].datasetIndex);`) → replace with:

```js
                   if (!els.length) return;
                   var dsHit = (state.chart.data.datasets || [])[els[0].datasetIndex] || {};
                   if (dsHit._forecast || dsHit._band) return;
                   if (d.forecastStart != null && d.forecast && els[0].index >= d.forecastStart) return;
                   drillFromChart(els[0].index, els[0].datasetIndex);
```

(g) `allInts` — forecast values are fractional; that is fine (the guard already yields normal ticks when any value is non-integer). No change needed; just don't "fix" it.

- [ ] **Step 5 — CSS.** Append to `static/css/reporting.css`:

```css
/* Forecast toggle + horizon (issue #168) */
.rs-forecast-horizon { font-size: 12px; padding: 2px 6px; border-radius: 8px;
  border: 1px solid var(--nx-border); background: var(--nx-card); color: inherit; }
#rsForecastToggle[disabled] { opacity: .4; cursor: not-allowed; }
```

- [ ] **Step 6 — Run the e2e, expect the toggle assertions GREEN** (the `rs-forecast-row` assertions stay RED until Task 6 — that is expected; run with `-k forecast_toggle` and accept the table-row failure, or split the test's tail into Task 6 if the executor prefers a green gate per task):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k forecast_toggle -q`

- [ ] **Step 7 — Commit:**

```bash
git add templates/_reporting_simple.html templates/js/_reporting_simple_js.html static/css/reporting.css tests/e2e/test_reporting_simple.py
git commit -F - <<'EOF'
feat(reporting): Simple forecast toggle, dashed extension, band

Chart toolbar gains a Forecast toggle plus an Auto/+7/+14/+30 horizon
select (single-date-dim + metric results only; greyed otherwise). The
toggle persists {enabled, horizon} inside the definition and re-runs;
the chart appends dashed accent lines bridged from the last actual
point, a shaded 95% band for single-metric results, and a disclaimer
note. Band/forecast datasets are legend-filtered and drill-inert (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 6: Simple — marked table rows + drill exclusion

**Files:**
- Modify: `templates/js/_reporting_simple_js.html` (`renderTable`)
- Modify: `static/css/reporting.css` (append-only)
- Test: `tests/e2e/test_reporting_simple.py` (Task 5's test tail goes green)

**Interfaces:**
- Consumes: Task 5's threading (`res.data.forecast`).
- Produces: forecast rows appended to the result table — `tr.is-forecast` + `data-testid="rs-forecast-row"`, bucket cell carries a "Forecast" badge, metric cells show ŷ; rows are excluded from row-click drill. KPI band/stat card/preview cache untouched (they read `rows`, which never contains forecast rows — D10).

- [ ] **Step 1 — Thread the block into `renderTable`.** Anchor the call site `renderTable(columns, rows);` (directly after the `var charted = …` line edited in Task 5) → `renderTable(columns, rows, res.data.forecast || null);`. Then change the definition `function renderTable(columns, rows) {` → `function renderTable(columns, rows, forecast) {`.

- [ ] **Step 2 — Append the rows.** Inside `renderTable`, directly after the `rows.forEach(function (r) {…});` loop that builds `html` rows and before `html += '</tbody></table>';`, add:

```js
    var fcRows = (forecast && !forecast.unavailable && (forecast.buckets || []).length)
      ? forecast : null;
    if (fcRows) {
      var mStart = columns.length - fcRows.series.length;
      fcRows.buckets.forEach(function (b, bi) {
        html += '<tr class="is-forecast" data-testid="rs-forecast-row">';
        for (var ci = 0; ci < columns.length; ci++) {
          if (ci === 0) {
            html += '<td>' + esc(String(b).slice(0, 10)) +
              ' <span class="rp-forecast-badge">' + esc(I18N.forecastLabel) + '</span></td>';
          } else if (ci >= mStart) {
            var sv = fcRows.series[ci - mStart];
            html += '<td class="reporting-ledger-num">' +
              esc(fmtChartTooltip(sv.values[bi])) + '</td>';
          } else {
            html += '<td></td>';
          }
        }
        html += '</tr>';
      });
    }
```

- [ ] **Step 3 — Exclude forecast rows from drill.** In the same function, the drill wiring iterates `el('rsTableWrap').querySelectorAll('tbody tr')` (anchor: `tr.addEventListener('click', function () { openDrill(clickedFor(rowValues)); });`) — change the selector to `'tbody tr:not(.is-forecast)'` so `rows[i]` alignment AND drill exclusion both hold.

- [ ] **Step 4 — CSS.** Append to `static/css/reporting.css`:

```css
.reporting-table tr.is-forecast td { font-style: italic; color: var(--nx-muted, #64748b); }
.rp-forecast-badge { display: inline-block; margin-left: 6px; padding: 1px 6px;
  font-size: 10px; font-style: normal; border-radius: 999px;
  background: color-mix(in srgb, var(--nx-accent) 14%, transparent);
  color: var(--nx-accent); vertical-align: 1px; }
```

- [ ] **Step 5 — Run, expect the FULL Task-5 e2e GREEN now:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py -k forecast_toggle -q`
Expected: PASS (toggle + 3 marked rows + toggle-off).

- [ ] **Step 6 — Commit:**

```bash
git add templates/js/_reporting_simple_js.html static/css/reporting.css
git commit -F - <<'EOF'
feat(reporting): Simple table gains marked forecast rows

Predicted buckets append to the result grid as italic rows with a
Forecast badge; the drill row-wiring selector skips them so predicted
points (which have no underlying rows) can never open the drill drawer.
KPI band, stat card and preview cache keep reading actuals only (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 3 — Advanced tab

### Task 7: Advanced — toggle in the results toolbar, viz + grid rendering

**Files:**
- Modify: `templates/reporting.html` (toolbar controls)
- Modify: `templates/js/_reporting_js.html` (state, buildDefinition, applyDefinition, renderResults)
- Modify: `templates/js/_reporting_viz_js.html` (`mountChart` opts.forecast)
- Test: `tests/e2e/test_reporting.py` (append)

**Interfaces:**
- Consumes: Task 4's payload block.
- Produces: `#rpForecast` checkbox (`data-testid="reporting-forecast-toggle"`) + `#rpForecastHorizon` select in the `#rpViewToggle` bar, shown only when `state.lastDef` is forecast-eligible; `buildDefinition()` emits `forecast` when enabled; `applyDefinition` restores it; the Advanced grid appends marked rows; `ReportingViz.mountChart` accepts `opts.forecast` and draws the dashed line + band when the selected X axis is the date dim and the Y axis matches a forecast series field.

- [ ] **Step 1 — Write the failing e2e test.** Append to `tests/e2e/test_reporting.py`, reusing that module's login + Advanced-tab helpers (Grep how the existing Advanced run tests stub `**/api/reporting/run` and press `reporting-run` — copy their stub payload shapes verbatim):

```python
def test_advanced_forecast_toggle_and_grid_rows(nexora_server, page):
    fc_block = {
        "anchor": "2025-08-01", "grain": "month", "method": "trend",
        "horizon": 3, "buckets": ["2025-09-01", "2025-10-01", "2025-11-01"],
        "series": [{"field": "doc_count", "values": [26.0, 28.0, 30.0],
                    "lower": [24.0, 25.5, 27.0], "upper": [28.0, 30.5, 33.0]}],
    }
    def run_stub(route):
        body = route.request.post_data_json or {}
        payload = {
            "columns": [{"field": "export_date"}, {"field": "doc_count"}],
            "rows": [[f"2025-{m:02d}-01", 10 + 2 * (m - 1)] for m in range(1, 9)],
            "rowCount": 8, "truncated": False, "resolvedDates": [],
        }
        if (body.get("forecast") or {}).get("enabled"):
            payload["forecast"] = fc_block
        route.fulfill(json=payload)
    page.route("**/api/reporting/run", run_stub)
    # ... module's own catalog stubs + login + build a 1-date-dim+metric
    # report in the Advanced builder + Run (copy the neighbouring test's
    # sequence), then:
    wrap = page.get_by_test_id("reporting-forecast-wrap")
    expect(wrap).to_be_visible()
    page.get_by_test_id("reporting-forecast-toggle").check()
    rows = page.get_by_test_id("rp-forecast-row")
    expect(rows).to_have_count(3)
    expect(rows.first).to_contain_text("Forecast")
```

- [ ] **Step 2 — Run, expect RED:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting.py -k advanced_forecast -q`

- [ ] **Step 3 — Toolbar markup.** In `templates/reporting.html`, inside `<div id="rpViewToggle" class="reporting-view-toggle" hidden data-testid="reporting-view-toggle">`, after the `rpViewPivot` button, add:

```html
        <label class="reporting-forecast-ctl" id="rpForecastWrap" hidden data-testid="reporting-forecast-wrap">
          <input type="checkbox" id="rpForecast" data-testid="reporting-forecast-toggle">
          <span>{{ _("Forecast") }}</span>
        </label>
        <select id="rpForecastHorizon" class="rs-forecast-horizon" hidden aria-label="{{ _('Forecast horizon') }}" data-testid="reporting-forecast-horizon">
          <option value="auto">{{ _("Auto") }}</option>
          <option value="7">+7</option>
          <option value="14">+14</option>
          <option value="30">+30</option>
        </select>
```

- [ ] **Step 4 — JS state + definition wiring.** In `templates/js/_reporting_js.html`:

(a) `buildDefinition()` currently `return { … };` a literal (anchor: `rowLimit: 5000,`). Refactor to:

```js
  function buildDefinition() {
    var d = {
      /* …existing literal body unchanged… */
    };
    if (state.forecast && state.forecast.enabled) d.forecast = state.forecast;
    return d;
  }
```

(b) eligibility + control sync — add near `renderResults` (module scope):

```js
  function forecastEligibleDef(def) {
    var cols = (def && def.columns) || [];
    return !!(def && def.kind !== 'sql' && cols.length === 1 && cols[0].grain &&
      Array.isArray(def.metrics) && def.metrics.length > 0);
  }
  function syncForecastCtl() {
    var wrap = document.getElementById('rpForecastWrap');
    var box = document.getElementById('rpForecast');
    var sel = document.getElementById('rpForecastHorizon');
    if (!wrap) return;
    var eligible = forecastEligibleDef(state.lastDef);
    wrap.hidden = !eligible;
    var on = eligible && !!(state.forecast && state.forecast.enabled);
    box.checked = on;
    sel.hidden = !on;
    if (!eligible) state.forecast = null;
  }
  document.getElementById('rpForecast').addEventListener('change', function () {
    var h = document.getElementById('rpForecastHorizon').value;
    state.forecast = this.checked
      ? { enabled: true, horizon: h === 'auto' ? 'auto' : parseInt(h, 10) } : null;
    run();
  });
  document.getElementById('rpForecastHorizon').addEventListener('change', function () {
    if (!state.forecast) return;
    var h = this.value;
    state.forecast.horizon = h === 'auto' ? 'auto' : parseInt(h, 10);
    run();
  });
```

> `run()` is a stand-in — Grep the actual function the `rpRun` click handler calls (anchor: `document.getElementById('rpRun').addEventListener('click', function () {`) and call that.

(c) `renderResults(data)` — anchor `state.lastResult = { columns: data.columns || [], rows: data.rows || [] };` → extend to `state.lastResult = { columns: data.columns || [], rows: data.rows || [], forecast: data.forecast || null };` and add `syncForecastCtl();` directly after that line. In the grid-building section (the loop that renders `data.rows` into the results table — Grep the `tbody`/row construction inside `renderResults`), after the data rows are appended, append forecast rows with the same cells-and-marker shape as Task 6 (class `is-forecast`, `data-testid="rp-forecast-row"`, badge span `rp-forecast-badge`, values via the module's own cell formatter). The grid there is DOM-built or string-built — match whichever idiom the loop uses; the Task 6 block is the reference for cell layout.

(d) `applyDefinition(def, name, id)` — after the `state.metrics = (def.metrics || [])…` restore block, add:

```js
    state.forecast = (def.forecast && def.forecast.enabled)
      ? { enabled: true, horizon: def.forecast.horizon || 'auto' } : null;
```

(e) chart mount — anchor `ReportingViz.mountChart(document.getElementById('rpChart'),` inside `setView`; extend the `chartOpts` line above it:

```js
      var chartOpts = canDrill(state.lastDef) ? { onElementClick: drillFromChart } : {};
      chartOpts.forecast = state.lastResult.forecast || null;
```

- [ ] **Step 5 — `ReportingViz.mountChart` forecast support.** In `templates/js/_reporting_viz_js.html`, inside `function draw()` (anchor: `lastChartXIndex = xi;\n      lastChartLabels = labels;`), after `var data = pairs.map(function (p) { return p.v; });` and the `lastChart…` assignments, add:

```js
      var fcRaw = opts.forecast;
      var fcSeries = null;
      if (fcRaw && !fcRaw.unavailable && (fcRaw.buckets || []).length &&
          xi === 0 && !truncated && (type === 'bar' || type === 'line')) {
        for (var fsi = 0; fsi < (fcRaw.series || []).length; fsi++) {
          var cYi = columns[yi];
          if (cYi && fcRaw.series[fsi].field === cYi.field) { fcSeries = fcRaw.series[fsi]; break; }
        }
      }
      var histN = labels.length;
      if (fcSeries) {
        labels = labels.concat(fcRaw.buckets.map(function (b) { return String(b).slice(0, 10); }));
        lastChartLabels = labels;
      }
```

then, after the existing `var ds = {…};` dataset object is built (anchor: `fill: type === 'line'`), pad + push the overlay datasets:

```js
      var chartDatasets = [ds];
      if (fcSeries) {
        ds.data = data.concat(fcRaw.buckets.map(function () { return null; }));
        var fcAccent2 = isDark ? '#818cf8' : '#4f46e5';
        var lead2 = [];
        for (var l2 = 0; l2 < histN - 1; l2++) lead2.push(null);
        var bridge2 = data[histN - 1];
        chartDatasets.push({
          label: colLabel(columns, yi) + ' · {{ _("Forecast") }}',
          data: lead2.concat([bridge2], fcSeries.values),
          type: 'line', borderColor: fcAccent2, borderDash: [6, 4], borderWidth: 2,
          backgroundColor: 'transparent', pointStyle: 'rectRot', fill: false, _forecast: true
        });
        chartDatasets.push({ label: '', data: lead2.concat([bridge2], fcSeries.upper),
          type: 'line', borderWidth: 0, pointRadius: 0, backgroundColor: 'transparent',
          fill: false, _band: true });
        chartDatasets.push({ label: '', data: lead2.concat([bridge2], fcSeries.lower),
          type: 'line', borderWidth: 0, pointRadius: 0,
          backgroundColor: isDark ? 'rgba(129,140,248,.18)' : 'rgba(79,70,229,.12)',
          fill: '-1', _band: true });
      }
```

and switch the `new Chart` data to `data: { labels: labels, datasets: chartDatasets },` (anchor: `data: { labels: labels, datasets: [ds] },`), add the same legend labels-filter as Task 5(f) to the `legend:` options, and guard `onClick` (anchor: `if (els.length) opts.onElementClick(els[0].index, els[0].datasetIndex);`) with:

```js
            if (!els.length) return;
            var hit = (this.data.datasets || [])[els[0].datasetIndex] || {};
            if (hit._forecast || hit._band) return;
            if (fcSeries && els[0].index >= histN) return;
            opts.onElementClick(els[0].index, els[0].datasetIndex);
```

> `isDark` does not exist yet at that point in `draw()` on some branches — it is defined a few lines below (`var isDark = document.documentElement.classList.contains('dark');`). Move that declaration above the forecast block rather than duplicating it.

- [ ] **Step 6 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/e2e/test_reporting.py -k advanced_forecast -q`

- [ ] **Step 7 — Commit:**

```bash
git add templates/reporting.html templates/js/_reporting_js.html templates/js/_reporting_viz_js.html tests/e2e/test_reporting.py
git commit -F - <<'EOF'
feat(reporting): Advanced forecast toggle, viz overlay, grid rows

The results toolbar gains a Forecast checkbox + horizon select (shown
for single-date-dim + metric definitions), buildDefinition emits and
applyDefinition restores the block, the grid appends marked prediction
rows, and ReportingViz.mountChart draws the dashed line + band when the
chart's X axis is the date dim and Y matches a forecast series (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 4 — Export + scheduled mails

### Task 8: Exports mark forecast rows (interactive `/api/reporting/export`)

**Files:**
- Modify: `nx_lib/views/reporting.py` (`api_export` + `_serialize_export`)
- Modify: `nx_lib/reporting/export.py` (`rows_to_xlsx` styling)
- Test: `tests/unit/test_reporting_export.py` (append), `tests/integration/test_reporting_routes.py` (append)

**Interfaces:**
- Consumes: Task 2's `compute_forecast` + `forecast_export_rows` (already imported in Task 4).
- Produces: a curated export whose definition has `forecast.enabled` gains the trailing marker column + prediction rows; `rows_to_xlsx(…, forecast_start=None)` styles rows from that index grey-italic. SQL-kind exports unchanged (no forecast — sql definitions have no grain metadata).

- [ ] **Step 1 — Failing unit test** (append to `tests/unit/test_reporting_export.py`, reusing its openpyxl round-trip idiom — Grep `load_workbook` there):

```python
def test_xlsx_forecast_rows_styled_italic():
    from openpyxl import load_workbook

    columns = [{"field": "d", "header": "Date"}, {"field": "n", "header": "Count"},
               {"field": "__forecast", "header": "Forecast"}]
    rows = [["2025-01-01", 10, ""], ["2025-02-01", 12, ""], ["2025-03-01", 14.0, "forecast"]]
    data = rows_to_xlsx(columns, rows, title="T", forecast_start=2)
    ws = load_workbook(io.BytesIO(data)).active
    # header_row is 4 without a chart; data rows follow
    assert ws.cell(row=5, column=3).value == ""
    fc_cell = ws.cell(row=7, column=1)
    assert fc_cell.font.italic
    assert ws.cell(row=7, column=3).value == "forecast"
```

- [ ] **Step 2 — Failing integration test** (append to `tests/integration/test_reporting_routes.py`, same patch pattern as Task 4 but against `/api/reporting/export` with `format: "csv"` so the assertion is plain text):

```python
def test_export_forecast_appends_marker_rows(admin_client):
    body = dict(_FC_DEF, format="csv")
    with (
        patch(
            "nx_lib.views.reporting._prepare_run",
            return_value=(_FC_COLS, "SELECT 1", [], None),
        ),
        patch("nx_lib.views.reporting._execute", return_value=_FC_ROWS),
    ):
        resp = admin_client.post("/api/reporting/export", json=body)
    assert resp.status_code == 200
    text = resp.data.decode("utf-8-sig")
    assert text.splitlines()[0].endswith("Forecast")
    assert text.count("forecast") == 3  # horizon 3 marker rows
```

- [ ] **Step 3 — Run both, expect RED:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_export.py tests/integration/test_reporting_routes.py -k forecast -q`

- [ ] **Step 4 — Implement.**

(a) `nx_lib/reporting/export.py` — `def rows_to_xlsx(columns, rows, *, title, chart_png=None, generated_at=None):` → add `forecast_start=None` to the signature, and in the data-row loop (anchor: `for r_off, row in enumerate(row_list, start=1):`) style predicted rows:

```python
    fc_font = Font(italic=True, color="6B7280")
    for r_off, row in enumerate(row_list, start=1):
        is_fc = forecast_start is not None and (r_off - 1) >= forecast_start
        for c_off, val in enumerate(row, start=1):
            cell = ws.cell(row=header_row + r_off, column=c_off, value=_safe_cell(val))
            if is_fc:
                cell.font = fc_font
```

(b) `nx_lib/views/reporting.py` — in `api_export`, on the **curated** path after `rows = _execute(engine, sql, params)` succeeds (anchor: the `return _serialize_export(\n        columns, rows, rd.get("title") or _("Report"), fmt, chart_png=chart_png\n    )` at the end of the function), insert before that return:

```python
    forecast_start = None
    fc_req = rd.get("forecast")
    if isinstance(fc_req, dict) and fc_req.get("enabled"):
        try:
            fc = compute_forecast(rd, columns, rows)
            if fc and not fc.get("unavailable"):
                columns, rows, forecast_start = forecast_export_rows(
                    columns, rows, fc, marker_header=_("Forecast")
                )
        except Exception as e:
            current_app.logger.warning(f"/api/reporting/export forecast skipped: {e}")
```

and pass it through: `return _serialize_export(columns, rows, …, chart_png=chart_png, forecast_start=forecast_start)`. Then extend `_serialize_export` (Grep `def _serialize_export`) with a `forecast_start=None` parameter forwarded to `rows_to_xlsx` only (csv needs nothing — the marker column is already in `columns`/`rows`).

- [ ] **Step 5 — Run, expect GREEN:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_export.py tests/integration/test_reporting_routes.py -k forecast -q`

- [ ] **Step 6 — Commit:**

```bash
git add nx_lib/reporting/export.py nx_lib/views/reporting.py tests/unit/test_reporting_export.py tests/integration/test_reporting_routes.py
git commit -F - <<'EOF'
feat(reporting): exports mark forecast rows, never as actuals

Curated exports whose definition has the forecast toggle on gain a
trailing Forecast marker column plus the prediction rows; xlsx styles
them grey-italic via a new forecast_start arg. CSV carries the marker
column so the distinction survives any downstream tool (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

### Task 9: Scheduled mails — PNG band + marked attachment rows (+ runner grainable fix)

**Files:**
- Modify: `nx_lib/reporting/chart_render.py` (`render_chart_png` forecast kwarg)
- Modify: `ops/run_scheduled_reports.py` (compute + thread the forecast)
- Modify: `nx_lib/reporting/runner.py` (missing `grainable_fields` on the table-provider validate — D9 latent bug)
- Test: `tests/unit/test_reporting_chart_render.py` (append), `tests/unit/test_reporting_runner.py` (append)

**Interfaces:**
- Consumes: Tasks 2–3.
- Produces: `render_chart_png(definition, columns, rows, *, …, forecast=None)` draws the dashed extension + `fill_between` band on the single-dim line/bar path; the scheduled runner computes the forecast when the saved definition's toggle is on and feeds both the PNG and the marker-row attachment; `runner.execute_definition` accepts table-source definitions that carry a grain.

- [ ] **Step 1 — Failing unit tests.**

(a) Append to `tests/unit/test_reporting_chart_render.py` (reuse its definition/rows fixtures — Grep the existing single-dim test):

```python
def test_render_chart_png_with_forecast_band():
    definition = {
        "columns": [{"field": "d", "grain": "month"}],
        "metrics": [{"metric": "n"}],
        "chartType": "line",
    }
    columns = [{"field": "d"}, {"field": "n"}]
    rows = [[f"2025-{m:02d}-01", 10 + m] for m in range(1, 7)]
    forecast = {
        "anchor": "2025-06-01", "grain": "month", "method": "trend", "horizon": 2,
        "buckets": ["2025-07-01", "2025-08-01"],
        "series": [{"field": "n", "values": [17.0, 18.0],
                    "lower": [15.0, 15.5], "upper": [19.0, 20.5]}],
    }
    png = render_chart_png(definition, columns, rows, forecast=forecast)
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    # the forecast must not crash the chartless fallback either
    assert render_chart_png(definition, columns, [], forecast=forecast) is None
```

(b) Append to `tests/unit/test_reporting_runner.py` — a table-provider definition WITH a grain validates (this is RED today; copy the file's existing table-provider test setup — Grep `provider` / the source-stub fixtures there and reuse them, adding `"grainable": True` to the date column and a `grain` on the definition column).

- [ ] **Step 2 — Run, expect RED:**

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_chart_render.py tests/unit/test_reporting_runner.py -k "forecast or grain" -q`

- [ ] **Step 3 — Implement `chart_render.py`.** Signature: `def render_chart_png(definition, columns, rows, *, width=8.0, height=4.5, dpi=110, forecast=None):`. In the `len(dims) == 1` branch, after the bar/line/pie plotting `if/elif/else` chain, add:

```python
            if (
                forecast
                and not forecast.get("unavailable")
                and forecast.get("buckets")
                and chart_type in ("line", "bar")
                and len(rows) <= MAX_X
            ):
                fx = [_label(b) for b in forecast["buckets"]]
                s0 = forecast["series"][0]
                bridge_x, bridge_y = [labels[-1]], [values[-1]]
                ax.plot(
                    bridge_x + fx,
                    bridge_y + list(s0["values"]),
                    color=_PALETTE[0], linestyle="--", marker="o", markersize=3,
                )
                ax.fill_between(
                    bridge_x + fx,
                    bridge_y + list(s0["lower"]),
                    bridge_y + list(s0["upper"]),
                    color=_PALETTE[0], alpha=0.15, linewidth=0,
                )
```

(Multi-dim results never get a forecast — D2 — so the multi-dim branch is untouched.)

- [ ] **Step 4 — Implement the runner fix.** In `nx_lib/reporting/runner.py`, the `provider == "table"` branch's `validate_report_definition(…)` call (anchor: the second `validate_report_definition(` in `execute_definition`, the one WITHOUT `grainable_fields=`) gains, mirroring the docprocessing branch above it:

```python
            grainable_fields={f["field"] for f in catalog if f.get("grainable")},
```

- [ ] **Step 5 — Implement the scheduled runner.** In `ops/run_scheduled_reports.py`:

(a) import (anchor: `from nx_lib.reporting.chart_render import render_chart_png`):

```python
from nx_lib.reporting.forecast import compute_forecast, forecast_export_rows
```

(b) after the main `columns, rows = execute_definition(` call and before `png = render_chart_png(definition, columns, rows)` (anchor: that exact line), insert + rewire:

```python
    forecast = None
    fdef = definition.get("forecast") if isinstance(definition, dict) else None
    if isinstance(fdef, dict) and fdef.get("enabled"):
        try:
            fc = compute_forecast(definition, columns, rows)
            if fc and not fc.get("unavailable"):
                forecast = fc
        except Exception as e:
            app.logger.warning(f"schedule {row.ScheduleID}: forecast skipped: {e}")
    png = render_chart_png(definition, columns, rows, forecast=forecast)
    forecast_start = None
    if forecast:
        columns, rows, forecast_start = forecast_export_rows(columns, rows, forecast)
```

> `app.logger.warning(f"schedule {row.ScheduleID}: …")` is the file's established per-schedule logging idiom (anchor: `app.logger.warning(f"schedule {row.ScheduleID}: chart render failed: {e}")`). The PNG must be rendered from the ORIGINAL columns/rows (the marker column would shift `metric_idx`); the attachment uses the marked ones. Thread `forecast_start` into the `rows_to_xlsx(columns, rows, title=…, chart_png=png)` call (anchor: `rows_to_xlsx(columns, rows, title=row.Name or "Report", chart_png=png),`) as `forecast_start=forecast_start`; the csv branch needs no change.

- [ ] **Step 6 — Run, expect GREEN** (plus the untouched suites for the touched modules):

Run: `C:\dev\nexora\.venv\Scripts\python -m pytest tests/unit/test_reporting_chart_render.py tests/unit/test_reporting_runner.py tests/unit/test_reporting_export.py -q`

- [ ] **Step 7 — Commit:**

```bash
git add nx_lib/reporting/chart_render.py nx_lib/reporting/runner.py ops/run_scheduled_reports.py tests/unit/test_reporting_chart_render.py tests/unit/test_reporting_runner.py
git commit -F - <<'EOF'
feat(reporting): scheduled mails carry the forecast when toggled on

render_chart_png gains a forecast kwarg (dashed extension plus
fill_between band on the single-dim path); the scheduled runner computes
the forecast for definitions with the toggle on, renders the PNG from
the raw series and appends marker rows to the attachment. Also fixes the
runner's table-provider validation missing grainable_fields, which
bounced any scheduled table-source report using a date grain (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

# PHASE 5 — Chores + full verify

### Task 10: i18n cycle, changelog, docs, full verify, live browser pass

**Files:**
- Modify: `messages.pot`, `translations/{de,fr,it}/LC_MESSAGES/messages.po` (+ compiled `.mo`)
- Modify: `CHANGELOG.md`, `docs/howto/reporting.md`

- [ ] **Step 1 — Babel cycle** (from repo root; **diff-sweep existing msgstr lines after `update`** — pybabel has silently mangled malformed `.po` lines before):

```powershell
.\.venv\Scripts\pybabel.exe extract -F babel.cfg -o messages.pot .
.\.venv\Scripts\pybabel.exe update -i messages.pot -d translations
```

Translate every new msgid in de/fr/it (non-fuzzy): "Forecast", "Forecast horizon", "Auto", "Dotted line and shaded band are forecast values, not actuals.", "Not enough history to forecast this series.", "Forecast requires one date breakdown with a metric." Then:

```powershell
.\.venv\Scripts\pybabel.exe compile -d translations
```

- [ ] **Step 2 — Changelog.** Under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- Reporting: forecast toggle on time-series results (#168) — single-date-dim
  reports gain a Forecast toggle + horizon control (Auto/+7/+14/+30) in Simple
  and Advanced; the chart extends with a dashed prediction line and a 95 %
  confidence band (stdlib trend + seasonality, `nx_lib/reporting/forecast.py`),
  the table appends marked prediction rows, exports carry a Forecast marker
  column, and scheduled mails include the forecast when the saved definition
  has the toggle on. Drill-through is excluded on predicted points.
```

Also under `### Fixed`:

```markdown
- Reporting: scheduled table-source reports with a date grain no longer fail
  validation in the runner (missing `grainable_fields`).
```

- [ ] **Step 3 — Docs.** In `docs/howto/reporting.md`, add a `## Forecast` section between `## Comparison & delta chips` and `## Dashboards` (match the file's heading style): what qualifies (one date-grained breakdown + metrics; owner-locked single-dim rule), how the toggle persists in the definition (`forecast: {enabled, horizon}`), the method in one paragraph (OLS trend + additive seasonal indices per grain, 95 % prediction interval, min-history rules from D3), the `unavailable` reasons, the marker-column export contract, scheduled-mail behaviour, and that drill-through never fires on predicted points. Update the `## Report-definition v1 JSON` section with the new optional `forecast` key.

- [ ] **Step 4 — Full verify:**

```powershell
.\.venv\Scripts\python scripts\test_db_reset.py
.\.venv\Scripts\python -m pytest tests --ignore=tests/e2e -q
.\.venv\Scripts\python -m pytest tests/e2e/test_reporting_simple.py tests/e2e/test_reporting.py -q
```

Expected: all green (incl. `test_translations.py` and `test_reporting_i18n_lint.py`).

- [ ] **Step 5 — Live browser pass.** Restart the server (`nx -r`), drive with Playwright (`nx -u -b --loginas:ben.streich`): open `/reporting`, build a Backlog History (or docprocessing doc-count) report broken down by month over `this_year`, toggle Forecast, verify the dashed line + band + marked table rows in light AND dark theme, click a forecast point (nothing must happen), export CSV and confirm the marker column, screenshot to `var/screenshots/` (send via SendUserFile when running remote).

- [ ] **Step 6 — Commit:**

```bash
git add messages.pot translations CHANGELOG.md docs/howto/reporting.md
git commit -F - <<'EOF'
docs(reporting): forecast changelog, howto section and i18n cycle

Changelog entries (feature + runner grainable fix), a Forecast section
plus the definition-JSON forecast key in docs/howto/reporting.md, and
the pybabel extract/update/translate/compile cycle for the new UI
strings (de/fr/it, non-fuzzy) (#168).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

## Gotchas & notes

- **Client zero-fill vs server forecast:** `zeroFillDateBuckets` fills the DISPLAY range from the definition's date filter — for a range ending in the future ("this year"), it fills zeros PAST the last data bucket, which would visually collide with the forecast (which anchors at the last DATA bucket, `forecast.anchor`). The Simple runs in this plan keep the two separate surfaces consistent because forecast rows/datasets are appended AFTER the zero-filled history; if a future-extending token range makes the chart show trailing zero buckets *and* a forecast, prefer trimming the fill at `forecast.anchor` in `zeroFillDateBuckets`' caller — check visually in Task 10 Step 5 and fix there if it bites.
- **`state.chartData.datasets` stays actual-only** — forecast datasets are built inside `renderChart`/`draw()` from `chartData.forecast`, so `writePreviewCache` (reads `datasets[0].data`) and the chart-type switcher never see forecast values.
- **Advanced `draw()` re-sorts on truncation** (`pairs.sort` when >50 categories) — that reorders X and would misalign the forecast; the `!truncated` guard in Task 7 Step 5 covers it. Same reason `render_chart_png` guards `len(rows) <= MAX_X`.
- **`_stub_run_ok` exists** in `tests/e2e/test_reporting_simple.py` but always returns the same payload — the forecast e2e needs its own stub that branches on the posted body (shown in Task 5). Don't retrofit `_stub_run_ok`.
- **`compare` and `forecast` coexist** — independent payload blocks, both bolt onto the same `payload` dict; the Simple pane posts `Object.assign({}, def, { compare: true })`, so `def.forecast` rides along automatically.
- **The AI surfaces tolerate the key:** `_validate_definition_for_user` strips only `chartHint` before validating; after Task 3 the `forecast` key validates cleanly, and `coerce_definition` ignores it. No AI prompt change in this plan (Owner action 2).
- **openpyxl row math in Task 8's unit test** assumes the chartless layout (`header_row = 4`); if the assertion lands one row off at execution time, print `ws.iter_rows` once and pin the actual indices — the styling logic itself is index-based on `forecast_start`, not on worksheet rows.
- **ruff line length is 100** — the code blocks above fit, but `ruff format` may rewrap; `git add -u` and recommit if the pre-commit hook rewrites.
- **fa-arrow-trend-up** is a Font Awesome 6 solid icon — the repo's chart toolbar already uses `fa-chart-column`/`fa-layer-group` from the same set.
- **Do not touch** `nx_lib/reporting/stats.py`, `runner.execute_definition`'s signature, or the drill drawer module (`_reporting_drill_js.html`) — exclusion happens at the click sites, not in the drawer.
