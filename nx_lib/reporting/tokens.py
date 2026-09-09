"""Relative-date tokens for report definitions.

A date filter's `value` may be {"token": "<name>"} (plus {"n": <int>} for
last_n_days) instead of literal dates. Tokens are validated at save/AI time
(schema.validate_report_definition) and resolved to absolute dates at RUN time
(views._prepare_run / runner.execute_definition), so saved and scheduled
reports never go stale.

Standalone on purpose: stdlib-only imports, so schema.py can import from here
without a cycle. Resolution uses datetime.date.today() (server-local) —
consistent with the AI prompt grounding; users have no stored timezone.
"This"-period tokens cover the FULL calendar period (future days simply match
no data), mirroring the Simple wizard's historical presetRange() semantics.
"""

import calendar
import datetime


def _day(d):
    return d, d


def _month_range(y, m):
    return datetime.date(y, m, 1), datetime.date(y, m, calendar.monthrange(y, m)[1])


def _month_start(d, delta):
    """First day of the month `delta` months from d's month."""
    total = d.year * 12 + (d.month - 1) + delta
    return datetime.date(total // 12, total % 12 + 1, 1)


def _week_of(d):
    start = d - datetime.timedelta(days=d.weekday())  # ISO Monday
    return start, start + datetime.timedelta(days=6)


def _quarter_start(d, delta=0):
    """First day of d's calendar quarter, shifted by `delta` quarters."""
    q_index = d.year * 4 + (d.month - 1) // 3 + delta
    year, q = divmod(q_index, 4)
    return datetime.date(year, q * 3 + 1, 1)


# Frozen vocabulary: name -> resolver(today) -> (start_date, end_date), inclusive.
# last_n_days is parameterized and handled explicitly in resolve_token.
RELATIVE_DATE_TOKENS = {
    "today": _day,
    "yesterday": lambda t: _day(t - datetime.timedelta(days=1)),
    "this_week": _week_of,
    "last_week": lambda t: _week_of(t - datetime.timedelta(days=7)),
    "this_month": lambda t: _month_range(t.year, t.month),
    "last_month": lambda t: _month_range(_month_start(t, -1).year, _month_start(t, -1).month),
    "this_quarter": lambda t: (
        _quarter_start(t),
        _quarter_start(t, 1) - datetime.timedelta(days=1),
    ),
    "last_quarter": lambda t: (
        _quarter_start(t, -1),
        _quarter_start(t) - datetime.timedelta(days=1),
    ),
    "this_year": lambda t: (datetime.date(t.year, 1, 1), datetime.date(t.year, 12, 31)),
    "last_year": lambda t: (datetime.date(t.year - 1, 1, 1), datetime.date(t.year - 1, 12, 31)),
    "last_3_months": lambda t: (_month_start(t, -2), _month_range(t.year, t.month)[1]),
    "last_n_days": None,
}

_N_MIN, _N_MAX = 1, 366


def validate_token_value(value):
    """Error message if `value` is not a well-formed token object, else None."""
    if not isinstance(value, dict):
        return 'relative-date value must be an object like {"token": "last_month"}'
    token = value.get("token")
    if token not in RELATIVE_DATE_TOKENS:
        allowed = ", ".join(sorted(RELATIVE_DATE_TOKENS))
        return (
            f"unknown relative-date token: {token!r} (allowed: {allowed}); "
            "tokens are only for relative ranges — for explicit dates pass "
            'literal ISO strings, e.g. "value": ["2026-06-01", "2026-06-30"]'
        )
    extra = set(value) - {"token", "n"}
    if extra:
        return f"unexpected keys in relative-date value: {sorted(extra)}"
    n = value.get("n")
    if token == "last_n_days":
        if isinstance(n, bool) or not isinstance(n, int) or not _N_MIN <= n <= _N_MAX:
            return f"last_n_days requires an integer n in [{_N_MIN}, {_N_MAX}]"
    elif n is not None:
        return f"token {token!r} takes no 'n'"
    return None


def resolve_token(value, today=None):
    """Inclusive (start_date, end_date) for one token value.

    Raises ValueError on a malformed value (callers normally validate first;
    this is the safety net for stale saved JSON).
    """
    err = validate_token_value(value)
    if err:
        raise ValueError(err)
    if today is None:
        today = datetime.date.today()
    if value["token"] == "last_n_days":
        return today - datetime.timedelta(days=value["n"] - 1), today
    resolver = RELATIVE_DATE_TOKENS[value["token"]]
    assert resolver is not None  # last_n_days (the only None entry) is handled above
    return resolver(today)


def resolve_definition_tokens(rd, today=None):
    """Replace token-valued filters with absolute half-open date pairs.

    Returns `rd` unchanged (same object identity) when no filter carries a
    token; otherwise returns a shallow copy whose token filters each become two
    literal clauses: field >= start AND field < end+1day. Half-open beats a
    resolved `between` because a datetime column would silently lose the end
    day's intraday rows. The op on a token filter is ignored (the validator
    only admits tokens with op 'between'). Raises ValueError on a bad token.
    """
    filters = (rd or {}).get("filters") or []
    if not any(
        isinstance(f, dict) and isinstance(f.get("value"), dict) and "token" in f.get("value", {})
        for f in filters
    ):
        return rd
    new_filters = []
    for f in filters:
        if not (
            isinstance(f, dict)
            and isinstance(f.get("value"), dict)
            and "token" in f.get("value", {})
        ):
            new_filters.append(f)
            continue
        start, end = resolve_token(f["value"], today)
        end_excl = end + datetime.timedelta(days=1)
        new_filters.append({"field": f["field"], "op": "gte", "value": start.isoformat()})
        new_filters.append({"field": f["field"], "op": "lt", "value": end_excl.isoformat()})
    out = dict(rd)
    out["filters"] = new_filters
    return out


def shifted_definition_for_comparison(rd, today=None):
    """Same definition with its single relative-date window shifted back by
    the window's own length: [start - len, start). Returns (shifted_rd,
    prior_start, prior_end) with inclusive display dates, or None when the
    definition has no token filter or more than one (ambiguous).

    # ponytail: token filters only — literal date ranges get no comparison;
    # extend via date_fields_from_catalog if that ceiling ever hurts.
    """
    filters = (rd or {}).get("filters") or []
    token_filters = [
        f
        for f in filters
        if isinstance(f, dict) and isinstance(f.get("value"), dict) and "token" in f["value"]
    ]
    if len(token_filters) != 1:
        return None
    f = token_filters[0]
    start, end = resolve_token(f["value"], today)
    end_excl = end + datetime.timedelta(days=1)
    length = end_excl - start
    prior_start, prior_end_excl = start - length, start
    new_filters = [x for x in filters if x is not f]
    new_filters.append({"field": f["field"], "op": "gte", "value": prior_start.isoformat()})
    new_filters.append({"field": f["field"], "op": "lt", "value": prior_end_excl.isoformat()})
    out = dict(rd)
    out["filters"] = new_filters
    return out, prior_start, prior_end_excl - datetime.timedelta(days=1)


# #178: how far back the forecast fit may reach beyond the visible window,
# per grain — enough buckets for the seasonal fit (day needs >= 2 weekday
# cycles; see forecast._SEASON_PERIODS) without scanning unbounded history.
_FORECAST_LOOKBACK_DAYS = {"day": 56, "week": 182, "month": 730, "quarter": 1460, "year": 2190}


def widened_definition_for_forecast(rd, today=None):
    """Same definition with its single relative-date window extended
    backwards by a grain-dependent lookback, so the forecast fit sees real
    history (weekend dips need weeks of daily buckets, not six days).

    Applies only to the forecastable shape: exactly one column WITH a grain,
    and exactly one token date filter (mirrors
    shifted_definition_for_comparison's token-only ceiling). Returns the
    widened copy (compare stripped — the caller only fits on it) or None.
    """
    cols = (rd or {}).get("columns") or []
    grain = cols[0].get("grain") if len(cols) == 1 and isinstance(cols[0], dict) else None
    lookback = _FORECAST_LOOKBACK_DAYS.get(grain) if grain is not None else None
    if lookback is None:
        return None
    filters = rd.get("filters") or []
    token_filters = [
        f
        for f in filters
        if isinstance(f, dict) and isinstance(f.get("value"), dict) and "token" in f["value"]
    ]
    if len(token_filters) != 1:
        return None
    f = token_filters[0]
    start, end = resolve_token(f["value"], today)
    new_filters = [x for x in filters if x is not f]
    # Same half-open shape as resolve_definition_tokens, so the fit's last bucket
    # sees the end day's intraday rows exactly like the visible series does.
    fit_start = start - datetime.timedelta(days=lookback)
    end_excl = end + datetime.timedelta(days=1)
    new_filters.append({"field": f["field"], "op": "gte", "value": fit_start.isoformat()})
    new_filters.append({"field": f["field"], "op": "lt", "value": end_excl.isoformat()})
    out = dict(rd)
    out["filters"] = new_filters
    out.pop("compare", None)
    return out


def date_fields_from_catalog(catalog):
    """Field keys that may carry a relative-date token: grainable (the
    docprocessing date fields) or date/datetime-typed (table sources)."""
    return {
        f["field"]
        for f in catalog or []
        if f.get("grainable") or str(f.get("type", "")).lower() in ("date", "datetime")
    }
