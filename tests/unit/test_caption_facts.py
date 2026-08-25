"""build_facts feeds the AI caption exact numbers over the WHOLE grid (it used to
see rows[:50] of an ascending time series -- the NULL bucket plus 2020)."""

from datetime import date

from nx_lib.reporting.caption_facts import build_facts

COLS = [{"field": "week", "header": "Woche"}, {"field": "page_count", "header": "PAGE_COUNT"}]


def _weeks(n, start=date(2020, 1, 27), value=lambda i: 30_000 + i):
    d = start
    out = []
    for i in range(n):
        out.append([f"{d.isoformat()} 00:00:00", value(i)])
        d = date.fromordinal(d.toordinal() + 7)
    return out


def test_null_bucket_is_reported_separately_and_never_as_peak():
    rows = [[None, 74_182], *_weeks(312)]
    facts = build_facts(COLS, rows, today=date(2026, 8, 25))
    assert "Rows with NO Woche (1): PAGE_COUNT 74182" in facts
    assert "312 buckets" in facts and "one per week" in facts
    assert f"total {sum(30_000 + i for i in range(312))}" in facts
    assert "peak 30311 (2026-01-12)" in facts  # the real max, not the NULL bucket
    assert "2020-01-27" in facts and "2026-01-12" in facts  # whole range, not the first 50


def test_partial_current_bucket_is_flagged():
    rows = _weeks(4, start=date(2026, 8, 3))  # last bucket starts Mon 2026-08-24
    facts = build_facts(COLS, rows, today=date(2026, 8, 25))
    assert "last bucket (2026-08-24) is the CURRENT, still-running week" in facts
    # Stats come from the three complete weeks; the running one is only in the total.
    assert "PAGE_COUNT: total 120006; 3 complete buckets with a value" in facts
    assert "peak 30002 (2026-08-17)" in facts
    assert "latest 30002 (2026-08-17) vs previous 30001 (2026-08-10)" in facts
    assert "current still-running bucket so far: 30003 (2026-08-24)" in facts
    facts_done = build_facts(COLS, rows, today=date(2026, 9, 10))
    assert "still-running" not in facts_done


def test_missing_and_zero_buckets_are_told_apart():
    rows = [["2026-01-01", 10], ["2026-02-01", None], ["2026-03-01", 0], ["2026-04-01", 40]]
    facts = build_facts(COLS, rows, today=date(2026, 8, 25))
    assert "3 buckets with a value, 1 with NO measurement (not zero), 1 at zero" in facts
    assert "one per month" in facts
    assert "latest 40 (2026-04-01) vs previous 0 (2026-03-01): n/a (baseline 0" in facts


def test_level_measure_reports_latest_not_sum():
    cols = [{"field": "d", "header": "Monat"}, {"field": "backlog", "header": "Backlog"}]
    rows = [["2026-01-01", 745], ["2026-02-01", 1183], ["2026-03-01", 369]]
    facts = build_facts(cols, rows, level_fields={"backlog"}, today=date(2026, 8, 25))
    assert "Backlog: latest 369 (2026-03-01); a level, so buckets must not be summed" in facts
    assert "total 2297" not in facts


def test_category_dimension_gives_top_shares_and_rest():
    cols = [{"field": "proc", "header": "Prozess"}, {"field": "n", "header": "Dokumente"}]
    rows = [[f"p{i}", (i + 1) * 100] for i in range(7)]
    facts = build_facts(cols, rows)
    assert "Prozess: 7 distinct values." in facts
    assert "Dokumente: total 2800; top: p6=700 (25%), p5=600 (21%)" in facts
    assert "other 2 values together 300" in facts


def test_totals_only_grid():
    cols = [
        {"field": "imported", "header": "Importiert"},
        {"field": "exported", "header": "Exportiert"},
    ]
    assert build_facts(cols, [[473_781, 457_798]]) == (
        "Rows: 1. Columns: Importiert, Exportiert.\nImportiert: 473781\nExportiert: 457798"
    )


def test_second_dimension_is_summed_per_bucket():
    cols = [
        {"field": "w", "header": "Woche"},
        {"field": "p", "header": "Prozess"},
        {"field": "n", "header": "N"},
    ]
    rows = [
        ["2026-08-03", "a", 1],
        ["2026-08-03", "b", 2],
        ["2026-08-10", "a", 5],
        ["2026-08-10", "b", None],
    ]
    facts = build_facts(cols, rows, today=date(2026, 9, 1))
    assert "N: total 8; 2 buckets with a value" in facts
    assert "N recent complete buckets: 2026-08-03=3, 2026-08-10=5." in facts
    assert "Further breakdown columns: Prozess" in facts


def test_empty_and_bare_string_columns():
    assert build_facts(["a"], []) == "Result is empty (0 rows)."
    assert "a: 3" in build_facts(["a"], [[3]])
