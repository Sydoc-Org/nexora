"""Unit tests for scripts/check-reporting-help-sync.py (the pre-commit nudge).

The script is hyphenated (not importable as a package), so it is loaded from
its file path, same as test_db_migrate.py does.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "reporting_help_sync_under_test",
        REPO_ROOT / "scripts" / "check-reporting-help-sync.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load()


def test_silent_when_no_reporting_files_staged():
    assert MOD.stale_help_warning(["nx_lib/db.py", "CHANGELOG.md"]) is None


def test_warns_when_behaviour_changed_without_help():
    warning = MOD.stale_help_warning(["templates/js/_reporting_simple_js.html"])
    assert warning is not None
    assert "templates/js/_reporting_simple_js.html" in warning


def test_silent_when_guide_updated_alongside():
    staged = ["templates/reporting.html", "docs/howto/reporting-guide.md"]
    assert MOD.stale_help_warning(staged) is None


def test_silent_when_tips_panel_updated_alongside():
    staged = ["nx_lib/views/reporting/pages.py", "templates/_reporting_help.html"]
    assert MOD.stale_help_warning(staged) is None


def test_warns_for_package_submodule_without_help():
    """A change under the reporting/ package trips the guard like the old
    single-file nx_lib/views/reporting.py used to."""
    warning = MOD.stale_help_warning(["nx_lib/views/reporting/pages.py"])
    assert warning is not None
    assert "nx_lib/views/reporting/pages.py" in warning


def test_help_partial_itself_does_not_trigger():
    assert MOD.stale_help_warning(["templates/_reporting_help.html"]) is None
