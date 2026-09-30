"""static/js/nx_sydoc.js: the pure period helpers shared by Sydoc Finance and
Sydoc BPS -- ISO weeks, the headline text of a period and the picker's month
grid (run under Node, see test_reporting_layout_view_js.py)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path("static/js/nx_sydoc.js")
NODE = shutil.which("node")
DASH = " \u2013 "  # the en dash the headline puts between the two ends
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

_HARNESS = """
const fs = require('fs');
global.window = { NX: {} };
global.document = {};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const V = window.NXSydoc;
"""


def _run(expr):
    js = _HARNESS + f"process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run(
        [NODE, "-e", js, str(SRC)], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return json.loads(out.stdout)


def test_iso_week_matches_iso_8601():
    assert _run("[V.isoWeek('2026-09-21'), V.isoWeek('2026-01-01'), V.isoWeek('2027-01-03')]") == [
        39,
        1,
        53,
    ]


def test_period_headline_names_a_month_a_week_a_span_and_a_range():
    out = _run("""[
      V.periodHeadline('2026-08-01','2026-08-31','en'),
      V.periodHeadline('2026-09-21','2026-09-27','en'),
      V.periodHeadline('2026-06-01','2026-08-31','en'),
      V.periodHeadline('2026-08-04','2026-08-19','en'),
      V.periodHeadline('2026-07-28','2026-08-03','en'),
      V.periodHeadline('2026-09-21','2026-09-27','de','Woche {n}')]""")
    assert out[0] == {"main": "August", "year": "2026", "kind": "month"}
    assert out[1] == {"main": "Week 39", "year": "2026", "kind": "week"}
    assert out[2] == {"main": f"Jun{DASH}Aug", "year": "2026", "kind": "months"}
    assert out[3] == {"main": f"4{DASH}19 Aug", "year": "2026", "kind": "range"}
    assert out[4]["main"] == f"28 Jul{DASH}3 Aug" and out[4]["kind"] == "range"
    assert out[5]["main"] == "Woche 39"


def test_iso_week_year_can_differ_from_the_calendar_year():
    out = _run("V.periodHeadline('2026-12-28','2027-01-03','en')")
    assert out == {"main": "Week 53", "year": "2026", "kind": "week"}


def test_month_cells_mark_future_months_disabled():
    cells = _run("V.monthCells(2026, '2026-09-30', 'en')")
    assert [c["key"] for c in cells][:2] == ["2026-01", "2026-02"]
    assert cells[8]["future"] is False and cells[9]["future"] is True
    assert cells[8]["current"] is True
    assert cells[0]["name"] == "Jan"


def test_fmt_substitutes_named_placeholders_and_keeps_unknown_ones():
    assert _run("V.fmt('{n} of {m} {x}', {n: 1, m: 2})") == "1 of 2 {x}"
