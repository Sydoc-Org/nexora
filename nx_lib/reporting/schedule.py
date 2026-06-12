"""Pure helpers for scheduled report delivery (no DB / Flask dependency).

The DB rows live in dbo.ReportSchedules; the runner (ops/run_scheduled_reports.py)
uses compute_next_run to advance a schedule after each send. Times are treated as
naive UTC to match SYSUTCDATETIME() columns.
"""

import copy
import re
from datetime import UTC, datetime, timedelta

FREQUENCIES = ("daily", "weekly", "monthly")
FORMATS = ("xlsx", "csv")
ALERT_OPS = ("gt", "gte", "lt", "lte")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utcnow():
    """Naive UTC 'now' (matches the SYSUTCDATETIME() columns)."""
    return datetime.now(UTC).replace(tzinfo=None)


def parse_recipients(s):
    """Split a comma/semicolon/whitespace-separated recipient string into a list."""
    return [p for p in re.split(r"[,;\s]+", (s or "").strip()) if p]


def valid_recipients(s):
    rec = parse_recipients(s)
    return bool(rec) and all(_EMAIL.match(r) for r in rec)


def validate_schedule(p):
    """Return an error string for an invalid schedule payload, else None."""
    if not isinstance(p, dict):
        return "invalid body"
    if p.get("frequency") not in FREQUENCIES:
        return "frequency must be daily, weekly or monthly"
    try:
        hour = int(p.get("hour"))
        minute = int(p.get("minute", 0))
    except (TypeError, ValueError):
        return "hour and minute must be integers"
    if not 0 <= hour <= 23:
        return "hour must be 0-23"
    if not 0 <= minute <= 59:
        return "minute must be 0-59"
    if (p.get("format") or "xlsx") not in FORMATS:
        return "format must be xlsx or csv"
    if not valid_recipients(p.get("recipients")):
        return "recipients must be one or more valid email addresses"
    if p.get("frequency") == "weekly":
        wd = p.get("weekday")
        if wd is None or not 0 <= int(wd) <= 6:
            return "weekday must be 0-6 (Mon-Sun) for a weekly schedule"
    if p.get("frequency") == "monthly":
        dom = p.get("dayOfMonth")
        if dom is None or not 1 <= int(dom) <= 28:
            return "dayOfMonth must be 1-28 for a monthly schedule"
    alert_op = p.get("alertOp")
    if alert_op:  # absent/empty = always send
        if alert_op not in ALERT_OPS:
            return "alertOp must be gt, gte, lt or lte"
        try:
            float(p.get("alertThreshold"))
        except (TypeError, ValueError):
            return "alertThreshold must be a number"
    return None


def compute_next_run(frequency, hour, minute, weekday, day_of_month, now):
    """Next run datetime strictly after `now` for the given recurrence (naive UTC).

    weekday: 0=Mon..6=Sun (weekly). day_of_month: 1..28 (monthly). `now` is the
    reference time (the runner passes datetime.utcnow()).
    """
    hour = int(hour)
    minute = int(minute)
    base = now.replace(second=0, microsecond=0)

    if frequency == "daily":
        cand = base.replace(hour=hour, minute=minute)
        if cand <= now:
            cand += timedelta(days=1)
        return cand

    if frequency == "weekly":
        wd = int(weekday if weekday is not None else 0)
        cand = base.replace(hour=hour, minute=minute)
        cand += timedelta(days=(wd - cand.weekday()) % 7)
        if cand <= now:
            cand += timedelta(days=7)
        return cand

    if frequency == "monthly":
        dom = max(1, min(28, int(day_of_month or 1)))
        cand = base.replace(day=dom, hour=hour, minute=minute)
        if cand <= now:
            year = cand.year + (1 if cand.month == 12 else 0)
            month = 1 if cand.month == 12 else cand.month + 1
            cand = cand.replace(year=year, month=month)
        return cand

    raise ValueError(f"unknown frequency: {frequency!r}")


def alert_trips(op, threshold, value):
    """True when `value` satisfies `<op> threshold` — the alert condition holds
    and the scheduled mail should go out. None / non-numeric values and unknown
    ops never trip (the runner then skips the mail instead of spamming)."""
    try:
        v = float(value)
        t = float(threshold)
    except (TypeError, ValueError):
        return False
    if op == "gt":
        return v > t
    if op == "gte":
        return v >= t
    if op == "lt":
        return v < t
    if op == "lte":
        return v <= t
    return False


def total_definition(definition):
    """Zero-column deep clone whose single result cell is the grand total of the
    definition's first metric — the Simple pane's stat-card trick, reused so the
    alert checks the same number the user sees (correct for avg/count_distinct).
    Returns None for definitions without metrics (incl. sql-kind); callers fall
    back to the row count."""
    if not isinstance(definition, dict) or not definition.get("metrics"):
        return None
    clone = copy.deepcopy(definition)
    clone["columns"] = []
    clone["sort"] = []
    return clone
