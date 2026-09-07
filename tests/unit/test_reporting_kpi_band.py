"""Reporting KPI band: the tiles say what they compute.

There is no JS runner in this repo, so — like `test_reporting_i18n_lint.py`
and PR #261's pre-paint assertions — this pins the arithmetic by reading the
source. It guards the four ways the band used to lie about a report with a
date dimension AND a second breakdown dimension ("Extraction correct % by
month / Field": 4 periods x 28 fields = 112 rows, one of those periods
being NULL):

1. `buckets` counted ROWS, so 112 rendered under "periods in the range"
   where there were 3 dated periods. Now it counts the leading dimension's
   distinct values, NULL excluded per (4) below.
2. `avg` is `total / cells`, and only claims "total ÷ buckets" when there
   is one row per period. Otherwise it says it is the mean of the cells.
3. The headline figure is captioned "Overall ... over every matching row"
   when it is the server's authoritative grand total for a non-additive
   metric (AVG over 29,756 rows), not "Total ... sum over the period".
4. Rows whose LEADING dimension is NULL are excluded, matching what the
   chart draws and what `caption_facts.build_facts` states. They used to be
   counted, which is how Peak came to label itself "null".

Both implementations are covered: Simple's `reporting_simple_result.js` and
the Advanced grid's mirror in `reporting_advanced.js`.
"""

import re
from pathlib import Path

import pytest

SIMPLE = Path("static/js/reporting_simple_result.js")
ADVANCED = Path("static/js/reporting_advanced.js")
SIMPLE_I18N = Path("templates/js/_reporting_simple_js.html")
ADVANCED_I18N = Path("templates/js/_reporting_js.html")


@pytest.fixture(scope="module")
def simple():
    return SIMPLE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def advanced():
    return ADVANCED.read_text(encoding="utf-8")


def _band(src):
    """The computeKpiBand function body."""
    m = re.search(r"function computeKpiBand\(.*?\n  \}\n", src, re.S)
    assert m, "computeKpiBand not found"
    return m.group(0)


@pytest.mark.parametrize("path", [SIMPLE, ADVANCED])
def test_buckets_counts_distinct_leading_dimension_values_not_rows(path):
    """`buckets` is what "periods in the range" claims. Counting rows made a
    28-field breakdown report 112 periods where there were 3."""
    body = _band(path.read_text(encoding="utf-8"))
    assert "var buckets = dims ? Object.keys(periods).length : cells;" in body
    # The two shapes of the old bug, in either implementation.
    assert "buckets = rows.length" not in body
    assert "buckets++" not in body


@pytest.mark.parametrize("path", [SIMPLE, ADVANCED])
def test_null_leading_dimension_rows_are_excluded(path):
    """The chart drops them and caption_facts excludes them from every stated
    figure; the band must agree or Peak labels itself "null"."""
    body = _band(path.read_text(encoding="utf-8"))
    assert "var kept = dims ? rows.filter(function (r) { return r[0] != null; }) : rows;" in body
    assert "if (!kept.length) return null;" in body
    # Every accumulator walks the filtered rows, never the raw ones.
    assert "rows.forEach(" not in body, "an accumulator still walks unfiltered rows"
    assert "kept.forEach(" in body


@pytest.mark.parametrize("path", [SIMPLE, ADVANCED])
def test_avg_divides_by_cells(path):
    """total/buckets is only the mean when there is one row per period; with a
    breakdown it silently mixed the two denominators."""
    body = _band(path.read_text(encoding="utf-8"))
    assert "avg: cells ? total / cells : 0" in body
    assert "total / buckets" not in body
    assert "cells: cells" in body, "the renderer needs cells to caption avg honestly"


def test_avg_caption_switches_when_cells_and_buckets_differ(simple, advanced):
    """ "Avg per bucket / total ÷ buckets" is only claimed when it is true."""
    assert "kpi.cells === kpi.buckets ? RS.I18N.kpiAvg : RS.I18N.kpiAvgCell" in simple
    assert "kpi.cells === kpi.buckets ? RS.I18N.kpiAvgSub" in simple
    assert "RS.I18N.kpiAvgCellSub.replace('{n}', kpi.cells)" in simple
    assert "kpi.cells === kpi.buckets ? I18N.kpiAvg : I18N.kpiAvgCell" in advanced


def test_non_additive_grand_total_is_not_called_a_sum(simple):
    """A metric aggregated with AVG/COUNT DISTINCT server-side yields one
    figure over every underlying row -- captioning it "Total ... sum over the
    period" claimed an addition nobody performed."""
    assert "agg: exact ? (aggs[n] || 'sum') : 'sum'," in simple
    assert "var isSum = !m.agg || m.agg === 'sum';" in simple
    assert "var caption = isSum ? RS.I18N.kpiTotal : RS.I18N.kpiOverall;" in simple
    assert "isSum ? RS.I18N.kpiSumSub : RS.I18N.kpiExactSub" in simple
    # The caption is no longer hardcoded to kpiTotal.
    assert "RS.esc(RS.I18N.kpiTotal) + (m.label" not in simple


def test_measure_totals_fallback_agrees_with_the_band(simple):
    """seriesIsHeadline compares measureTotals' figure against the band's own
    sum; if only one of them drops the NULL-dimension rows the sparkline and
    delta chip disappear for every report that has any."""
    assert (
        "var summable = dims ? rows.filter(function (r) { return r[0] != null; }) : rows;" in simple
    )
    assert (
        "summable.forEach(function (r) { if (isNumericCell(r[idx])) total += Number(r[idx]); });"
        in simple
    )


def test_every_new_i18n_key_is_translatable_and_defined():
    """The keys the renderers now read must exist, and go through gettext."""
    simple_i18n = SIMPLE_I18N.read_text(encoding="utf-8")
    advanced_i18n = ADVANCED_I18N.read_text(encoding="utf-8")
    for key in ("kpiOverall", "kpiExactSub", "kpiAvgCell", "kpiAvgCellSub"):
        assert re.search(rf"\b{key}: \{{\{{ _\(", simple_i18n), f"{key} missing from Simple"
    assert re.search(r"\bkpiAvgCell: \{\{ _\(", advanced_i18n), "kpiAvgCell missing from Advanced"
