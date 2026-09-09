"""static/js/reporting_layout_view.js: seriesFor() picks column 0 as labels
and every all-numeric column as a dataset (run under Node, see
test_reporting_grid_js.py)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path("static/js/reporting_layout_view.js")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

_HARNESS = """
const fs = require('fs');
global.window = { NX: {} };
global.document = {};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const V = window.ReportingLayoutView;
const cols = [{field:'import_date'},{field:'doc_count'},{field:'client'},{field:'pages'}];
const rows = [['2026-01-01', 3, 'A', 12], ['2026-01-02', null, 'B', 7], ['2026-01-03', 5, 'A', 'n/a']];
process.stdout.write(JSON.stringify(V.seriesFor(cols, rows, {columns:[{field:'import_date', grain:'day'}]})));
"""


def test_series_for_uses_first_column_as_labels_and_numeric_columns_as_datasets():
    out = json.loads(
        subprocess.run(
            [NODE, "-e", _HARNESS, str(SRC)], capture_output=True, text=True, check=True
        ).stdout
    )
    assert out["labels"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert [d["label"] for d in out["datasets"]] == ["doc_count"]  # pages has 'n/a' → not numeric
    assert out["datasets"][0]["data"] == [3, None, 5]


_PIVOT_HARNESS = """
const fs = require('fs');
global.window = { NX: {} };
global.document = {};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const V = window.ReportingLayoutView;
const cols = [{field:'Datum'},{field:'Kunde'},{field:'hours'}];
const rows = [['2026-08-01', 'A', '938.4499'], ['2026-08-01', 'B', '2.0000'], ['2026-09-01', 'A', '10']];
process.stdout.write(JSON.stringify(V.seriesFor(cols, rows, {})));
"""


def test_series_for_coerces_numeric_strings_and_pivots_second_dimension():
    out = subprocess.run(
        [NODE, "-e", _PIVOT_HARNESS, str(SRC)], capture_output=True, text=True, check=True
    )
    s = json.loads(out.stdout)
    assert s["labels"] == ["2026-08-01", "2026-09-01"]
    assert [d["label"] for d in s["datasets"]] == ["A", "B"]
    assert s["datasets"][0]["data"] == [938.4499, 10]
    assert s["datasets"][1]["data"] == [2, None]
