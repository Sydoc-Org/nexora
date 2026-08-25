"""Fact sheet for the auto AI caption (Surface D).

The caption model used to be handed the first 50 raw rows of the result grid.
For a 313-week time series sorted ascending that is the NULL-date bucket plus
the weeks of 2020 -- it never saw the other 260 weeks, called the NULL bucket
"a clear outlier" and reported "at most 3,712 pages in the latest weeks"
(2026-08-25 audit). It now gets exact facts computed here over the WHOLE grid:
it cannot mis-aggregate, and there is no sample left to hallucinate a pattern
from. Pure module: no Flask, no DB, deterministic output.

Input is the grid the client displays -- ``columns`` as ``[{field, header}]``
(or bare strings), ``rows`` as lists. The first non-numeric column is the
dimension; every numeric column is a measure. Output is plain-text lines for
the prompt (see ``nx_lib.reporting.ai.caption``).
"""

import re
from datetime import date, timedelta
from itertools import pairwise
from statistics import fmean

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")
RECENT_POINTS = 6  # the tail the model may narrate movement from
SAMPLE_POINTS = 12  # evenly spaced sample across a long series


def _is_num(v):
    return isinstance(v, int | float) and not isinstance(v, bool)


def _fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return str(int(round(v))) if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
    return str(v)


def _pct(new, base):
    if base is None or new is None or base == 0:
        return "n/a (baseline 0 or missing)"
    return f"{(new - base) / abs(base) * 100:+.0f}%"


def _label(v):
    """Dimension label; None for NULL/empty (rows with no value for the dimension)."""
    if v is None or v == "":
        return None
    s = str(v)
    return s[:10] if _ISO.match(s) else s


def _grain(dates):
    if len(dates) < 2:
        return None
    gaps = sorted(d for d in ((b - a).days for a, b in pairwise(dates)) if d > 0)
    if not gaps:
        return None
    g = gaps[len(gaps) // 2]  # median gap survives a few missing buckets
    if g == 1:
        return "day"
    if 6 <= g <= 8:
        return "week"
    if 28 <= g <= 31:
        return "month"
    if 89 <= g <= 92:
        return "quarter"
    if 365 <= g <= 366:
        return "year"
    return None


def _bucket_end(start, grain):
    """Exclusive end of the bucket that starts at ``start``."""
    if grain == "day":
        return start + timedelta(days=1)
    if grain == "week":
        return start + timedelta(days=7)
    if grain == "month":
        return (start.replace(day=1) + timedelta(days=32)).replace(day=1)
    if grain == "quarter":
        m = start.month - (start.month - 1) % 3 + 3
        return date(start.year + (m > 12), m if m <= 12 else m - 12, 1)
    if grain == "year":
        return date(start.year + 1, 1, 1)
    return start


def _group(labels, values):
    """label -> summed value (None when every row for that label is None).

    A second dimension (week x process) repeats labels; summing per label gives
    the same numbers the chart's stacked view shows.
    """
    out = {}
    for lab, v in zip(labels, values, strict=True):
        if lab not in out:
            out[lab] = None
        if v is not None:
            out[lab] = (out[lab] or 0) + v
    return out


def _sample(items, k):
    if len(items) <= k:
        return items
    step = (len(items) - 1) / (k - 1)
    return [items[round(i * step)] for i in range(k)]


def _series_lines(name, series, *, level):
    present = [(lab, v) for lab, v in series if v is not None]
    missing = len(series) - len(present)
    if not present:
        return [f"{name}: no values."]
    nums = [v for _, v in present]
    zeros = sum(1 for v in nums if v == 0)
    peak = max(present, key=lambda p: p[1])
    low = min(present, key=lambda p: p[1])
    head = (
        f"{name}: latest {_fmt(nums[-1])} ({present[-1][0]}); a level, so buckets must not be summed"
        if level
        else f"{name}: total {_fmt(sum(nums))}"
    )
    head += f"; {len(present)} buckets with a value"
    if missing:
        head += f", {missing} with NO measurement (not zero)"
    if zeros:
        head += f", {zeros} at zero"
    head += (
        f"; avg per bucket {_fmt(fmean(nums))}; peak {_fmt(peak[1])} ({peak[0]}); "
        f"low {_fmt(low[1])} ({low[0]})."
    )
    out = [head]
    if len(present) >= 2:
        (pl, pv), (ll, lv) = present[-2], present[-1]
        out.append(
            f"{name} latest {_fmt(lv)} ({ll}) vs previous {_fmt(pv)} ({pl}): {_pct(lv, pv)}."
        )
    if len(present) >= 4:
        half = len(present) // 2
        a, b = fmean(nums[:half]), fmean(nums[half:])
        out.append(
            f"{name} avg per bucket, first half {_fmt(a)} vs second half {_fmt(b)}: {_pct(b, a)}."
        )
    out.append(
        f"{name} recent: "
        + ", ".join(f"{lab}={_fmt(v)}" for lab, v in present[-RECENT_POINTS:])
        + "."
    )
    if len(present) > RECENT_POINTS:
        out.append(
            f"{name} sampled across the whole range: "
            + ", ".join(f"{lab}={_fmt(v)}" for lab, v in _sample(present, SAMPLE_POINTS))
            + "."
        )
    return out


def _category_lines(name, groups):
    present = [(lab, v) for lab, v in groups.items() if v is not None]
    if not present:
        return [f"{name}: no values."]
    total = sum(v for _, v in present)
    top = sorted(present, key=lambda p: -p[1])[:5]

    def share(v):
        return f" ({v / total * 100:.0f}%)" if total else ""

    line = f"{name}: total {_fmt(total)}; top: " + ", ".join(
        f"{lab}={_fmt(v)}{share(v)}" for lab, v in top
    )
    rest = len(present) - len(top)
    if rest > 0:
        line += f"; other {rest} values together {_fmt(total - sum(v for _, v in top))}"
    return [line + "."]


def build_facts(columns, rows, *, level_fields=(), today=None):
    """Return the fact-sheet text for ``columns``/``rows``.

    ``level_fields``: field or header names of measures that are *levels*
    (a backlog): their headline is the latest value, never a sum over buckets.
    ``today``: injectable for tests; decides whether the last time bucket is
    the still-running one.
    """
    today = today or date.today()
    cols = [
        ((c.get("field") or c.get("header") or ""), (c.get("header") or c.get("field") or ""))
        if isinstance(c, dict)
        else (str(c), str(c))
        for c in columns or []
    ]
    n = len(cols)
    rows = [list(r)[:n] + [None] * (n - len(r)) for r in rows]
    if not rows:
        return "Result is empty (0 rows)."
    num_idx = [
        i
        for i in range(n)
        if any(_is_num(r[i]) for r in rows) and all(r[i] is None or _is_num(r[i]) for r in rows)
    ]
    dim_idx = [i for i in range(n) if i not in num_idx]
    lines = [f"Rows: {len(rows)}. Columns: {', '.join(h for _, h in cols)}."]

    if not dim_idx:
        for i in num_idx:
            vals = [r[i] for r in rows if r[i] is not None]
            lines.append(
                f"{cols[i][1]}: {_fmt(sum(vals)) if vals else 'n/a'}"
                + (f" (over {len(rows)} rows)" if len(rows) > 1 else "")
            )
        return "\n".join(lines)

    d = dim_idx[0]
    dname = cols[d][1]
    labels = [_label(r[d]) for r in rows]
    null_rows = [r for r, lab in zip(rows, labels, strict=True) if lab is None]
    if null_rows:
        parts = []
        for i in num_idx:
            vals = [r[i] for r in null_rows if r[i] is not None]
            parts.append(f"{cols[i][1]} {_fmt(sum(vals)) if vals else 'n/a'}")
        lines.append(
            f"Rows with NO {dname} ({len(null_rows)}): {', '.join(parts)} -- these have no "
            f"{dname} value; NOT a period or category, never an outlier, excluded from everything below."
        )
    data = [(lab, r) for lab, r in zip(labels, rows, strict=True) if lab is not None]
    if not data:
        return "\n".join(lines)
    data_labels = [lab for lab, _ in data]

    if all(_ISO.match(lab) for lab in data_labels):
        dates = sorted({date.fromisoformat(lab) for lab in data_labels})
        grain = _grain(dates)
        lines.append(
            f"Time axis {dname}: {len(dates)} buckets from {dates[0]} to {dates[-1]}"
            + (f", one per {grain}" if grain else "")
            + "."
        )
        if grain and dates[-1] <= today < _bucket_end(dates[-1], grain):
            lines.append(
                f"The last bucket ({dates[-1]}) is the CURRENT, still-running {grain}: its value is "
                "incomplete and not comparable to finished buckets -- never call it a drop."
            )
        for i in num_idx:
            series = sorted(_group(data_labels, [r[i] for _, r in data]).items())
            level = cols[i][0] in level_fields or cols[i][1] in level_fields
            lines += _series_lines(cols[i][1], series, level=level)
    else:
        lines.append(f"{dname}: {len(_group(data_labels, [None] * len(data)))} distinct values.")
        for i in num_idx:
            lines += _category_lines(cols[i][1], _group(data_labels, [r[i] for _, r in data]))

    if len(dim_idx) > 1:
        lines.append(
            f"Further breakdown columns: {', '.join(cols[i][1] for i in dim_idx[1:])} -- the facts "
            f"above are summed over them per {dname}."
        )
    return "\n".join(lines)
