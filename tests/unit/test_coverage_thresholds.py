"""Per-module coverage thresholds (MIN_COVERAGE) — the source-of-truth targets.

NOTE: these checks are INFORMATIONAL, not a hard gate. An in-suite test can
only read the previous run's coverage.xml (pytest-cov writes it at session
end), so asserting on it false-failed the whole suite on stale/partial data.
The per-module test now reports coverage as a skip. MIN_COVERAGE remains the
ratchet target — raise entries as coverage improves, never lower without
sign-off — and is intended to feed a future post-pytest enforcement step."""

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
    "octo.py": 95,
    "outage.py": 95,
    "process_helpers.py": 100,
    "extensions.py": 100,
    "app_logging.py": 100,
    "cli.py": 70,
    "cli_doctor.py": 60,
    "views/core.py": 95,
    "views/auth.py": 65,
    "views/profile.py": 75,
    "views/dashboard.py": 25,
    # views/admin.py split into views/admin/ (Task 16, beautify-phase-0-1);
    # baselines below are the measured per-submodule values at split time.
    "views/admin/clients.py": 85,
    "views/admin/logs.py": 60,
    "views/admin/organizations.py": 85,
    "views/admin/overview.py": 70,
    "views/admin/permissions.py": 65,
    "views/admin/processes.py": 85,
    "views/admin/system.py": 55,
    "views/admin/users.py": 75,
    "views/workitems.py": 35,
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
    """Informational only — this is NOT a hard gate.

    pytest-cov writes coverage.xml at session *end*, so an in-suite test can
    only ever read the PREVIOUS run's file — or a partial one left by a
    targeted ``--cov`` run. That made a hard assertion false-fail the entire
    suite on stale/partial data, so the per-module check now reports coverage
    as a skip rather than failing.

    To inspect real coverage, open var/test-results/coverage-html after a full
    run. To re-enable hard enforcement, move this check to a post-pytest step
    (a standalone script run after coverage.xml is freshly written) rather than
    an in-suite test. MIN_COVERAGE above stays the source of truth for that.
    """
    pcts = _load_coverage_pct_per_file()  # skips if coverage.xml is absent
    actual = pcts.get(module, 0.0)
    pytest.skip(
        f"{module}: {actual:.1f}% (target {min_pct}%) — informational; in-suite "
        f"coverage gating disabled because it reads a stale coverage.xml."
    )
