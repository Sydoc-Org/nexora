"""Sydoc BPS -- the hours booked in the BPS timetool, and which of them are billed (#415).

Pure and DB-free, like nx_lib/finance.py. The timetool's export lands in
SYDOC_Statistik.dbo.BPS_ProjectReport (the ``bps_projects`` reporting source,
0124): one row per booking with customer (Kunde), project package
(Projektpaket), task (Aufgabe), person (Benutzer), date, hours and a comment.
BPS has no billing flag; what is billed is a property of the task name, and
it lives here, once, for both the Finance page (every billable booking,
singly, with its comment) and the Sydoc BPS page (all hours, drilled down).

The billable rule is expressed as ``BILLABLE_RULES``: a list of AND-groups in
the Reporting filter grammar, OR-ed together -- the generic 'table' provider
only ANDs, so each group is its own query and the groups are disjoint by
construction. ``is_billable`` is the same rule in Python for rows that are
already in memory (the BPS page's tree); tests keep the two in step.
"""

from __future__ import annotations

import datetime as dt
import html
from decimal import Decimal

from .reporting.semantic import resolve_metrics
from .reporting.table_query import build_generic_query

SOURCE = "bps_projects"

#: Tasks billed to the customer they are booked on.
BILLABLE_TASKS = (
    "Support-verrechenbar",
    "Support extern verrechenbar",
    "Change",
    "Change Request",
    "Professional Services",
    "Projektmanagement",
)
#: Sydoc's own customers: work booked on them is never billed, whatever the task.
INTERNAL_CUSTOMERS = ("sydoc", "sydoc intern")
#: Customer of vacation, sick leave, compensation -- not work at all.
ABSENCES = "Absences"
#: File preparation is billed only on Privera's new-dossier stream.
PREPARATION = ("Vorbereitung Akten", "Privera", "Tagesgeschäft Neuzugänge")

BILLABLE_RULES = (
    (
        {"field": "Aufgabe", "op": "in", "value": list(BILLABLE_TASKS)},
        {"field": "Kunde", "op": "not_in", "value": list(INTERNAL_CUSTOMERS)},
    ),
    (
        {"field": "Aufgabe", "op": "eq", "value": PREPARATION[0]},
        {"field": "Kunde", "op": "eq", "value": PREPARATION[1]},
        {"field": "Projektpaket", "op": "eq", "value": PREPARATION[2]},
    ),
)

#: The row-level columns of a booking, in display order.
BOOKING_COLUMNS = (
    "Datum",
    "Kunde",
    "Projektpaket",
    "Aufgabe",
    "Benutzer",
    "Stunden",
    "Beschreibung",
)


def _norm(value):
    """SQL Server compares strings ignoring trailing blanks (and the data has
    them: 'Support intern (nicht verrechenbar) '); do the same, case-insensitively
    like the default collation."""
    return (value or "").rstrip().casefold()


_BILLABLE_TASKS_N = {_norm(t) for t in BILLABLE_TASKS}
_INTERNAL_N = {_norm(c) for c in INTERNAL_CUSTOMERS}


def is_billable(task, customer, package):
    """The BILLABLE_RULES decision for one booking, in Python."""
    if _norm(task) in _BILLABLE_TASKS_N and _norm(customer) not in _INTERNAL_N:
        return True
    return (_norm(task), _norm(customer), _norm(package)) == tuple(_norm(p) for p in PREPARATION)


def category(task, customer, package):
    """'billable' | 'absence' | 'service' -- the three colours of the BPS page."""
    if _norm(customer) == _norm(ABSENCES):
        return "absence"
    return "billable" if is_billable(task, customer, package) else "service"


def clean_text(value):
    """A BPS text cell for display: the export carries HTML entities (&amp;) and
    stray leading/trailing blanks."""
    if value is None:
        return None
    return html.unescape(str(value)).strip()


def clean_name(value):
    """A person's name with the export's doubled inner blanks collapsed."""
    text = clean_text(value)
    return " ".join(text.split()) if text else text


# --------------------------------------------------------------------------
# The period of the BPS page
# --------------------------------------------------------------------------

MAX_RANGE_DAYS = 366


def parse_range(start, end, today=None):
    """``from``/``to`` query values (ISO dates) -> (first, last) inclusive dates.

    The default is the previous calendar month (what is being invoiced). A
    range longer than a year is cut to a year back from its end; an inverted
    one is swapped; anything unparseable falls back to the default.
    """
    today = today or dt.date.today()
    first_this = today.replace(day=1)
    last_prev = first_this - dt.timedelta(days=1)
    default = (last_prev.replace(day=1), last_prev)
    try:
        first = dt.date.fromisoformat(str(start))
        last = dt.date.fromisoformat(str(end))
    except ValueError:
        return default
    if last < first:
        first, last = last, first
    if (last - first).days >= MAX_RANGE_DAYS:
        first = last - dt.timedelta(days=MAX_RANGE_DAYS - 1)
    return first, last


def range_filters(first, last):
    """Half-open date filters over Datum, bound as ISO strings (the legacy ODBC
    driver cannot bind a Python date -- HYC00)."""
    return [
        {"field": "Datum", "op": "gte", "value": first.isoformat()},
        {"field": "Datum", "op": "lt", "value": (last + dt.timedelta(days=1)).isoformat()},
    ]


# --------------------------------------------------------------------------
# Queries and payloads of the BPS page
# --------------------------------------------------------------------------

SUMMARY_ROW_CAP = 20000
ENTRIES_ROW_CAP = 5000
#: The hierarchy the page drills through; the entries endpoint filters on these.
DIMENSIONS = ("Aufgabe", "Kunde", "Projektpaket", "Benutzer")
_TOTALS = {
    "hours": {"aggregation": "sum", "base_field": "Stunden", "filter": None},
    "count": {"aggregation": "count", "base_field": None, "filter": None},
}


class BpsSpecError(ValueError):
    """The registered bps_projects source lacks a column the page needs."""


def _require(catalog, fields):
    have = {c["field"] for c in catalog}
    missing = [f for f in fields if f not in have]
    if missing:
        raise BpsSpecError(f"bps_projects lacks {', '.join(missing)}")
    return have


def summary_queries(base_object, catalog, first, last):
    """(combos, days): hours and bookings per task/customer/package/person, and
    per day/task/customer/package (the chart's categories need all three)."""
    fields = _require(catalog, (*DIMENSIONS, "Datum", "Stunden"))
    resolved = resolve_metrics([{"metric": "hours"}, {"metric": "count"}], _TOTALS, fields)
    out = []
    for dims in (DIMENSIONS, ("Datum", "Aufgabe", "Kunde", "Projektpaket")):
        rd = {
            "columns": [{"field": d} for d in dims],
            "filters": range_filters(first, last),
            "metrics": [{"metric": "hours"}, {"metric": "count"}],
            "sort": [],
        }
        out.append(
            build_generic_query(
                rd, base_object, catalog, row_cap=SUMMARY_ROW_CAP, resolved_metrics=resolved
            )
        )
    return out


def entries_query(base_object, catalog, first, last, where):
    """Raw bookings of the range, narrowed by exact matches on DIMENSIONS.

    `where` maps a dimension to its value; None/'' is not a filter. The
    Reporting grammar has no "is blank" for eq, and BPS never leaves these
    empty (the columns are NOT NULL), so that is all the page needs.
    """
    _require(catalog, BOOKING_COLUMNS)
    filters = range_filters(first, last)
    for dim in DIMENSIONS:
        value = (where or {}).get(dim)
        if value not in (None, ""):
            filters.append({"field": dim, "op": "eq", "value": value})
    rd = {
        "columns": [{"field": c} for c in BOOKING_COLUMNS],
        "filters": filters,
        "sort": [{"field": "Datum", "dir": "asc"}, {"field": "Benutzer", "dir": "asc"}],
    }
    return build_generic_query(rd, base_object, catalog, row_cap=ENTRIES_ROW_CAP)


def _num(value):
    if value is None:
        return 0
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        return int(value) if value.is_integer() else round(value, 4)
    return int(value)


def _day(value):
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)[:10]


def summary_payload(combo_rows, day_rows, first, last):
    """The page payload: one row per task/customer/package/person, the daily
    series per category, and the headline totals.

    Names are cleaned (entities, doubled blanks) and rows that clean to the
    same key are merged, so "Astrid  Schicker" and "Astrid Schicker" are one
    person.
    """
    merged: dict[tuple, dict] = {}
    for r in combo_rows:
        task, customer, package, person = (
            clean_text(r[0]),
            clean_text(r[1]),
            clean_text(r[2]),
            clean_name(r[3]),
        )
        key = (task, customer, package, person)
        row = merged.setdefault(
            key,
            {
                "task": task,
                "customer": customer,
                "package": package,
                "person": person,
                "category": category(task, customer, package),
                "hours": 0,
                "count": 0,
            },
        )
        row["hours"] = _num(row["hours"] + _num(r[4]))
        row["count"] += _num(r[5])
    rows = sorted(merged.values(), key=lambda x: -x["hours"])

    days = {}
    d = first
    while d <= last:
        days[d.isoformat()] = {"date": d.isoformat(), "billable": 0, "service": 0, "absence": 0}
        d += dt.timedelta(days=1)
    for r in day_rows:
        bucket = days.get(_day(r[0]))
        if bucket is None:
            continue
        cat = category(clean_text(r[1]), clean_text(r[2]), clean_text(r[3]))
        bucket[cat] = _num(bucket[cat] + _num(r[4]))

    totals = {"hours": 0, "billable": 0, "service": 0, "absence": 0, "count": 0}
    for r in rows:
        totals["hours"] = _num(totals["hours"] + r["hours"])
        totals[r["category"]] = _num(totals[r["category"]] + r["hours"])
        totals["count"] += r["count"]
    totals["people"] = len({r["person"] for r in rows if r["category"] != "absence"})
    return {
        "from": first.isoformat(),
        "to": last.isoformat(),
        "rows": rows,
        "days": list(days.values()),
        "totals": totals,
        "truncated": len(combo_rows) >= SUMMARY_ROW_CAP,
    }


def entries_payload(rows):
    """Raw booking rows -> [{date, customer, package, task, person, hours, comment, category}]."""
    out = []
    for r in rows:
        task, customer, package = clean_text(r[3]), clean_text(r[1]), clean_text(r[2])
        out.append(
            {
                "date": _day(r[0]),
                "customer": customer,
                "package": package,
                "task": task,
                "person": clean_name(r[4]),
                "hours": _num(r[5]),
                "comment": clean_text(r[6]),
                "category": category(task, customer, package),
            }
        )
    return out
