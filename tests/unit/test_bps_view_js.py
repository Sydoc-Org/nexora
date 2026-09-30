"""static/js/bps_view.js: the Sydoc BPS drill-down's pure logic -- squarified
treemap, gain/loss against the previous period, zoom levels and the per-day
grouping of a leaf's bookings (run under Node, see
test_reporting_layout_view_js.py)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path("static/js/bps_view.js")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

_HARNESS = """
const fs = require('fs');
global.window = { NX: {} };
global.document = {};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const V = window.BpsView;
"""

ROWS = (
    "[{task:'A',customer:'X',person:'p',hours:3,count:1,category:'billable'},"
    "{task:'A',customer:'Y',person:'q',hours:1,count:2,category:'service'},"
    "{task:'B',customer:'X',person:'p',hours:2,count:1,category:'service'}]"
)
PREV = "[{task:'A',customer:'X',person:'p',hours:1,count:1,category:'billable'}]"
ORDER = "['Aufgabe','Kunde','Benutzer']"


def _run(expr):
    js = _HARNESS + f"process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run(
        [NODE, "-e", js, str(SRC)], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return json.loads(out.stdout)


def test_squarify_fills_the_area_and_keeps_order():
    rects = _run("V.squarify([{h:6},{h:6},{h:4},{h:3},{h:2},{h:2},{h:1}], 600, 400)")
    assert len(rects) == 7
    area = sum(r["w"] * r["h"] for r in rects)
    assert abs(area - 600 * 400) < 1e-6
    assert all(
        r["x"] >= -1e-9
        and r["y"] >= -1e-9
        and r["x"] + r["w"] <= 600 + 1e-6
        and r["y"] + r["h"] <= 400 + 1e-6
        for r in rects
    )
    assert [r["i"] for r in rects] == list(range(7))


def test_squarify_of_nothing_is_empty():
    assert _run("V.squarify([], 600, 400)") == []


def test_delta_says_new_flat_up_or_down():
    assert _run("[V.delta(5,0).dir, V.delta(0,0).dir, V.delta(12,10).dir, V.delta(9,10).dir]") == [
        "new",
        "flat",
        "up",
        "down",
    ]
    assert _run("V.delta(12,10)") == {"dir": "up", "ratio": 0.2, "diff": 2}


def test_level_zooms_along_the_order_and_sums_prev():
    top = _run(f"V.level({ROWS}, {PREV}, {ORDER}, [])")
    assert [(g["key"], g["hours"], g["prev"]) for g in top] == [("A", 4, 1), ("B", 2, 0)]
    assert top[0]["billable"] == 3 and top[0]["cat"] == "partly"
    assert top[1]["cat"] == "service"
    zoomed = _run(f"V.level({ROWS}, {PREV}, {ORDER}, ['A'])")
    assert [g["key"] for g in zoomed] == ["X", "Y"]
    assert zoomed[0]["cat"] == "billable" and zoomed[0]["prev"] == 1


def test_prev_total_follows_the_path():
    assert _run(f"[V.prevTotal({PREV}, {ORDER}, []), V.prevTotal({PREV}, {ORDER}, ['B'])]") == [
        1,
        0,
    ]


def test_by_day_groups_entries_and_totals_them():
    out = _run(
        "V.byDay([{date:'2026-08-04',hours:2},{date:'2026-08-03',hours:1.5},{date:'2026-08-03',hours:0.5}])"
    )
    assert [(d["date"], d["hours"], len(d["entries"])) for d in out] == [
        ("2026-08-03", 2, 2),
        ("2026-08-04", 2, 1),
    ]
