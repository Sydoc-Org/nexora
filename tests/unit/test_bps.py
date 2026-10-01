"""The BPS billable rule, period parsing and the /bps page payloads (#415).

nx_lib/bps.py is pure. The billable rule exists twice -- as filter groups the
SQL builder runs (BILLABLE_RULES) and as is_billable() for rows already in
memory -- and these tests keep the two in step, against the task / customer
strings the PROD export actually carries (trailing blanks included).
"""

import datetime as dt
from decimal import Decimal

import pytest

from nx_lib import bps
from nx_lib.reporting.table_query import table_source_catalog

CATALOG = table_source_catalog(
    [
        {"field": "Datum", "type": "date", "grainable": True},
        {"field": "Kunde", "type": "string"},
        {"field": "Projektpaket", "type": "string"},
        {"field": "Aufgabe", "type": "string"},
        {"field": "Benutzer", "type": "string"},
        {"field": "Stunden", "type": "number"},
        {"field": "Beschreibung", "type": "string"},
    ]
)


def _rule_matches(rule, task, customer, package):
    """Evaluate one BILLABLE_RULES group the way SQL Server would (trailing
    blanks ignored, case-insensitive default collation)."""
    row = {"Aufgabe": task, "Kunde": customer, "Projektpaket": package}

    def norm(v):
        return (v or "").rstrip().casefold()

    for c in rule:
        v = norm(row[c["field"]])
        if c["op"] == "eq" and v != norm(c["value"]):
            return False
        if c["op"] == "in" and v not in {norm(x) for x in c["value"]}:
            return False
        if c["op"] == "not_in" and v in {norm(x) for x in c["value"]}:
            return False
    return True


CASES = [
    ("Support-verrechenbar", "Privera", "Tagesgeschäft Invoice", True),
    ("Support extern verrechenbar", "Generali", "Support", True),
    ("Change", "Bucherer", "EasyTax", True),
    ("Change Request", "Elektro Material", "Invoice", True),
    ("Professional Services", "Michel Gruppe", "DPS", True),
    ("Projektmanagement", "SSD_physisch", "Projekt", True),
    ("Vorbereitung Akten", "Privera", "Tagesgeschäft Neuzugänge", True),
    ("Vorbereitung Akten", "Privera", "Neuzugänge", False),
    ("Vorbereitung Akten", "Stadt LU", "Tagesgeschäft", False),
    ("Change", "sydoc", "IT", False),
    ("Projektmanagement", "sydoc intern", "Intern", False),
    ("Support-nicht verrechenbar", "Privera", "Invoice", False),
    ("Professional Services - nicht verrechenbar", "Aveniq", "Xpert", False),
    ("Support intern (nicht verrechenbar) ", "sydoc intern", "Intern", False),
    ("Vacation", "Absences", "Absences", False),
    ("Change ", "ISS", "Hypotheken ", True),  # trailing blanks, as SQL ignores them
]


@pytest.mark.parametrize("task,customer,package,expected", CASES)
def test_is_billable_and_the_sql_rules_agree(task, customer, package, expected):
    assert bps.is_billable(task, customer, package) is expected
    sql_says = any(_rule_matches(r, task, customer, package) for r in bps.BILLABLE_RULES)
    assert sql_says is expected


def test_the_rules_are_disjoint_so_merging_them_never_double_counts():
    for task, customer, package, _ in CASES:
        hits = sum(_rule_matches(r, task, customer, package) for r in bps.BILLABLE_RULES)
        assert hits <= 1


def test_category_separates_absence_billable_and_other_service():
    assert bps.category("Vacation", "Absences", "Absences") == "absence"
    assert bps.category("Change", "ISS", "x") == "billable"
    assert bps.category("Validierung", "Privera", "Tagesgeschäft Invoice") == "service"


def test_clean_text_and_name_undo_the_exports_quirks():
    assert bps.clean_text(" CR Hypotheken &amp; Reporting ") == "CR Hypotheken & Reporting"
    assert bps.clean_name("Astrid  Schicker") == "Astrid Schicker"
    assert bps.clean_text(None) is None


# --------------------------------------------------------------------------
# The period
# --------------------------------------------------------------------------

TODAY = dt.date(2026, 9, 30)


def test_parse_range_defaults_to_the_previous_month():
    assert bps.parse_range(None, None, TODAY) == (dt.date(2026, 8, 1), dt.date(2026, 8, 31))
    assert bps.parse_range("x", "2026-09-01", TODAY) == (dt.date(2026, 8, 1), dt.date(2026, 8, 31))


def test_parse_range_swaps_an_inverted_range_and_caps_it_at_a_year():
    assert bps.parse_range("2026-09-10", "2026-09-01", TODAY) == (
        dt.date(2026, 9, 1),
        dt.date(2026, 9, 10),
    )
    first, last = bps.parse_range("2020-01-01", "2026-09-30", TODAY)
    assert last == dt.date(2026, 9, 30) and (last - first).days == bps.MAX_RANGE_DAYS - 1


def test_range_filters_are_half_open_iso_strings():
    """The legacy ODBC driver cannot bind a date (HYC00): bind strings."""
    assert bps.range_filters(dt.date(2026, 8, 1), dt.date(2026, 8, 31)) == [
        {"field": "Datum", "op": "gte", "value": "2026-08-01"},
        {"field": "Datum", "op": "lt", "value": "2026-09-01"},
    ]


# --------------------------------------------------------------------------
# Queries and payloads
# --------------------------------------------------------------------------


def test_summary_queries_group_by_the_hierarchy_and_by_day():
    combos, days = bps.summary_queries(
        "dbo.BPS_ProjectReport", CATALOG, dt.date(2026, 8, 1), dt.date(2026, 8, 31)
    )
    sql, params = combos
    assert "GROUP BY [Aufgabe], [Kunde], [Projektpaket], [Benutzer]" in sql
    assert "SUM([Stunden])" in sql and "COUNT(*)" in sql
    assert params == ["2026-08-01", "2026-09-01"]
    assert "GROUP BY [Datum], [Aufgabe], [Kunde], [Projektpaket]" in days[0]


def test_summary_queries_fail_loudly_without_a_needed_column():
    trimmed = [c for c in CATALOG if c["field"] != "Benutzer"]
    with pytest.raises(bps.BpsSpecError, match="Benutzer"):
        bps.summary_queries("dbo.X", trimmed, dt.date(2026, 8, 1), dt.date(2026, 8, 31))


def test_entries_query_filters_only_on_given_dimensions():
    sql, params = bps.entries_query(
        "dbo.BPS_ProjectReport",
        CATALOG,
        dt.date(2026, 8, 1),
        dt.date(2026, 8, 31),
        {"Aufgabe": "Change", "Kunde": "ISS", "Benutzer": "", "Projektpaket": None},
    )
    assert "[Aufgabe] = ? AND [Kunde] = ?" in sql
    assert "[Benutzer] = ?" not in sql and "[Projektpaket] = ?" not in sql
    assert params == ["2026-08-01", "2026-09-01", "Change", "ISS"]
    assert sql.startswith("SELECT TOP (5000) [Datum], [Kunde]")


def test_summary_payload_merges_cleaned_names_and_fills_every_day():
    combos = [
        ("Change", "ISS", "Hypotheken", "Anna  Muster", Decimal("1.3333"), 1),
        ("Change", "ISS", "Hypotheken", "Anna Muster", Decimal("0.6667"), 2),
        ("Validierung", "Privera", "Tagesgeschäft Invoice", "Ben", Decimal("4"), 3),
        ("Vacation", "Absences", "Absences", "Cem", Decimal("8.4"), 1),
    ]
    days = [
        (dt.date(2026, 8, 3), "Change", "ISS", "Hypotheken", Decimal("2")),
        (dt.date(2026, 8, 3), "Vacation", "Absences", "Absences", Decimal("8.4")),
        (dt.date(2026, 8, 4), "Validierung", "Privera", "x", Decimal("4")),
    ]
    p = bps.summary_payload(combos, days, dt.date(2026, 8, 3), dt.date(2026, 8, 5))
    anna = [r for r in p["rows"] if r["person"] == "Anna Muster"]
    assert len(anna) == 1 and anna[0]["hours"] == 2 and anna[0]["count"] == 3
    assert anna[0]["category"] == "billable"
    assert [d["date"] for d in p["days"]] == ["2026-08-03", "2026-08-04", "2026-08-05"]
    assert p["days"][0] == {"date": "2026-08-03", "billable": 2, "service": 0, "absence": 8.4}
    assert p["days"][2] == {"date": "2026-08-05", "billable": 0, "service": 0, "absence": 0}
    t = p["totals"]
    assert t["hours"] == 14.4 and t["billable"] == 2 and t["service"] == 4 and t["absence"] == 8.4
    assert t["people"] == 2  # the absence-only person does not count as working
    assert p["truncated"] is False


def test_entries_payload_cleans_and_categorises_each_booking():
    rows = [
        (
            dt.date(2026, 8, 4),
            "Bucherer",
            "EasyTax",
            "Change",
            "Matthias  P",
            Decimal("0.75"),
            "ITHD &amp; x ",
        )
    ]
    assert bps.entries_payload(rows) == [
        {
            "date": "2026-08-04",
            "customer": "Bucherer",
            "package": "EasyTax",
            "task": "Change",
            "person": "Matthias P",
            "hours": 0.75,
            "comment": "ITHD & x",
            "category": "billable",
        }
    ]


def test_previous_range_is_the_previous_month_for_a_whole_month():
    assert bps.previous_range(dt.date(2026, 8, 1), dt.date(2026, 8, 31)) == (
        dt.date(2026, 7, 1),
        dt.date(2026, 7, 31),
    )
    assert bps.previous_range(dt.date(2026, 3, 1), dt.date(2026, 3, 31)) == (
        dt.date(2026, 2, 1),
        dt.date(2026, 2, 28),
    )


def test_previous_range_is_the_same_length_just_before_otherwise():
    assert bps.previous_range(dt.date(2026, 9, 21), dt.date(2026, 9, 27)) == (
        dt.date(2026, 9, 14),
        dt.date(2026, 9, 20),
    )
    assert bps.previous_range(dt.date(2026, 6, 1), dt.date(2026, 8, 31)) == (
        dt.date(2026, 3, 1),
        dt.date(2026, 5, 31),
    )


def test_next_range_is_the_next_month_or_the_next_span_and_stops_at_today():
    today = dt.date(2026, 9, 30)
    assert bps.next_range(dt.date(2026, 8, 1), dt.date(2026, 8, 31), today) == (
        dt.date(2026, 9, 1),
        dt.date(2026, 9, 30),
    )
    assert bps.next_range(dt.date(2026, 9, 14), dt.date(2026, 9, 20), today) == (
        dt.date(2026, 9, 21),
        dt.date(2026, 9, 27),
    )
    assert bps.next_range(dt.date(2026, 9, 1), dt.date(2026, 9, 30), today) is None


def test_months_query_sums_hours_per_calendar_month():
    sql, params = bps.months_query("dbo.BPS_ProjectReportAll", CATALOG)
    assert "DATEFROMPARTS(YEAR([Datum]), MONTH([Datum]), 1)" in sql
    assert "GROUP BY" in sql and params == []


def test_span_query_asks_for_the_oldest_and_newest_booking_dates():
    sql, params = bps.span_query("dbo.BPS_ProjectReportAll", CATALOG)
    assert "MIN([Datum])" in sql and "MAX([Datum])" in sql and params == []
    assert bps.span_payload([(dt.date(2025, 1, 3), dt.datetime(2026, 9, 30, 0, 0))]) == {
        "first": "2025-01-03",
        "latest": "2026-09-30",
    }
    assert bps.span_payload([(None, None)]) == {"first": None, "latest": None}
    assert bps.span_payload([]) == {"first": None, "latest": None}


def test_months_payload_keys_by_yyyy_mm_and_drops_empty_months():
    rows = [
        (dt.date(2025, 1, 1), Decimal("12.5")),
        (dt.date(2026, 8, 1), Decimal("1300.5")),
        (dt.date(2026, 9, 1), None),
        (None, Decimal("3")),
    ]
    assert bps.months_payload(rows) == {"2025-01": 12.5, "2026-08": 1300.5}


def test_whole_month_spans_step_by_months_both_ways():
    today = dt.date(2026, 9, 30)
    assert bps.previous_range(dt.date(2026, 7, 1), dt.date(2026, 9, 30)) == (
        dt.date(2026, 4, 1),
        dt.date(2026, 6, 30),
    )
    assert bps.next_range(dt.date(2026, 3, 1), dt.date(2026, 5, 31), today) == (
        dt.date(2026, 6, 1),
        dt.date(2026, 8, 31),
    )
    assert bps.previous_range(dt.date(2025, 11, 1), dt.date(2026, 1, 31)) == (
        dt.date(2025, 8, 1),
        dt.date(2025, 10, 31),
    )


def test_next_range_keeps_the_shape_of_the_period():
    today = dt.date(2026, 9, 30)
    # Jun-Aug is followed by Sep-Nov and week 39 by week 40, even where they
    # run past today; only a period that would start after today is refused.
    assert bps.next_range(dt.date(2026, 6, 1), dt.date(2026, 8, 31), today) == (
        dt.date(2026, 9, 1),
        dt.date(2026, 11, 30),
    )
    assert bps.next_range(dt.date(2026, 9, 21), dt.date(2026, 9, 27), today) == (
        dt.date(2026, 9, 28),
        dt.date(2026, 10, 4),
    )
    assert bps.next_range(dt.date(2026, 9, 28), dt.date(2026, 10, 4), today) is None


def test_a_month_so_far_compares_with_the_same_days_of_the_month_before():
    assert bps.previous_range(dt.date(2026, 9, 1), dt.date(2026, 9, 29)) == (
        dt.date(2026, 8, 1),
        dt.date(2026, 8, 29),
    )
    # February has no 29th/30th: 1-30 Mar compares with all of February.
    assert bps.previous_range(dt.date(2026, 3, 1), dt.date(2026, 3, 30)) == (
        dt.date(2026, 2, 1),
        dt.date(2026, 2, 28),
    )
