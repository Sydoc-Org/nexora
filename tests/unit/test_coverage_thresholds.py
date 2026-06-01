"""Per-module coverage thresholds. Each entry is the minimum line-coverage %
the module must hit before the test suite is allowed to pass. Thresholds
ratchet upward as Phase 1/2/3 tasks land — never lower an entry; instead
raise it as coverage improves."""

from pathlib import Path

import pytest

# defusedxml protects against XXE / billion-laughs. coverage.xml is locally
# generated, but using the safe parser is cheap defense in depth.
# ET is the canonical alias for ElementTree across the Python stdlib + ecosystem.
from defusedxml import ElementTree as ET  # noqa: N817

COVERAGE_XML = Path(__file__).resolve().parents[2] / "var" / "test-results" / "coverage.xml"

# Keys are paths relative to the [tool.coverage.run] source root (nx_lib/) —
# that's how coverage.xml records them when source = ["nx_lib"]. Don't add
# the "nx_lib/" prefix here or the lookup will miss every entry.
#
# Start values reflect the post-Phase-0 baseline. After each Phase-1 task
# lands, raise the corresponding entry to the new measured value. Ratchet
# upward only — never lower a threshold without team sign-off.
MIN_COVERAGE = {
    "security.py": 80,
    "files.py": 100,
    "users.py": 100,
    "db.py": 85,
    "i18n.py": 100,
    "maintenance.py": 100,
    "middleware.py": 100,
    "hooks.py": 100,
    "notifications.py": 100,
    "octo.py": 95,
    "process_helpers.py": 100,
    "extensions.py": 100,
    "app_logging.py": 100,
    "cli.py": 0,
    "cli_doctor.py": 0,
    "views/core.py": 0,
    "views/auth.py": 30,
    "views/profile.py": 0,
    "views/dashboard.py": 0,
    "views/admin.py": 0,
    "views/workitems.py": 0,
    "views/invoices.py": 0,
    "views/notifications.py": 0,
    "views/chat.py": 0,
    # views/generali.py intentionally excluded — covered by the Generali
    # phase-2 plan.
}


def _load_coverage_pct_per_file():
    """Parse var/test-results/coverage.xml into {filename: line_rate_pct}."""
    if not COVERAGE_XML.exists():
        pytest.skip(f"coverage.xml not generated yet at {COVERAGE_XML}")
    tree = ET.parse(COVERAGE_XML)
    root = tree.getroot()
    out = {}
    for cls in root.iter("class"):
        filename = cls.get("filename", "").replace("\\", "/")
        line_rate = float(cls.get("line-rate", 0)) * 100.0
        out[filename] = line_rate
    return out


@pytest.mark.parametrize("module,min_pct", sorted(MIN_COVERAGE.items()))
def test_module_coverage_meets_threshold(module, min_pct):
    """A module missing from coverage.xml is treated as 0% — this happens when
    pytest is invoked against a subset of tests that don't import the module.
    Thresholds with min_pct=0 still pass in that case; thresholds > 0 will
    fail loudly and prompt the developer to run the full suite."""
    pcts = _load_coverage_pct_per_file()
    actual = pcts.get(module, 0.0)
    assert actual >= min_pct, (
        f"{module} coverage dropped: {actual:.1f}% < threshold {min_pct}%. "
        f"Either add tests, or (with team sign-off) lower the threshold. "
        f"(If {module} is absent from coverage.xml, run the full pytest suite.)"
    )
