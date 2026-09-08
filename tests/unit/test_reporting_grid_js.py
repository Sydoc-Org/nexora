"""static/js/reporting_grid.js: the pure helpers the drag/resize engine is
built on, run under Node (the repo has no JS test runner; see
test_reporting_kpi_band.py for the read-the-source alternative)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path("static/js/reporting_grid.js")
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

_HARNESS = """
const fs = require('fs');
global.window = {};
global.document = { addEventListener() {} };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const G = window.ReportingGrid;
const out = {
  clamp: [G.clampInt('7', 1, 12, 6), G.clampInt(0, 1, 12, 6), G.clampInt('x', 1, 12, 6), G.clampInt(13, 1, 12, 6)],
  geom: G.geomStyle(8, 3),
  fwd: G.moveIndex(['a', 'b', 'c', 'd'], 0, 2),
  back: G.moveIndex(['a', 'b', 'c', 'd'], 3, 1),
  same: G.moveIndex(['a', 'b'], 1, 1),
};
process.stdout.write(JSON.stringify(out));
"""


def _run():
    res = subprocess.run(
        [NODE, "-e", _HARNESS, str(SRC)], capture_output=True, text=True, check=True
    )
    return json.loads(res.stdout)


def test_clamp_int_parses_and_bounds():
    assert _run()["clamp"] == [7, 1, 6, 12]


def test_geom_style_matches_dashboard_css_contract():
    assert _run()["geom"] == "grid-column:span 8;--rdb-cardrows:3"


def test_move_index_forward_lands_after_hovered_and_backward_before():
    out = _run()
    assert out["fwd"] == ["b", "c", "a", "d"]
    assert out["back"] == ["a", "d", "b", "c"]
    assert out["same"] == ["a", "b"]
