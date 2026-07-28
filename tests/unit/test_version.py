"""The app version is single-sourced (nx_lib/version.py) and the footer derives
from it via a context processor — no hardcoded duplicate that can drift.
"""

import re
import tomllib
from pathlib import Path

from nx_lib.version import BUILD_STAMP, __version__

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_version_matches_pyproject():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_footer_template_uses_injected_version_not_a_literal():
    tpl = (REPO_ROOT / "templates" / "_nexora_version.html").read_text(encoding="utf-8")
    assert "{{ nexora_version }}" in tpl
    # No hardcoded x.y.z that can drift away from pyproject.
    assert not re.search(r"\b\d+\.\d+\.\d+\b", tpl)


def test_context_processor_injects_version():
    from nx_lib.hooks import _inject_app_version

    assert _inject_app_version() == {
        "nexora_version": __version__,
        "nexora_build": BUILD_STAMP,
    }


def test_build_stamp_is_empty_without_generated_module():
    # nx_lib/_build.py is deploy-generated and gitignored, so a checkout must
    # degrade to version-only rather than raising at import.
    assert not (REPO_ROOT / "nx_lib" / "_build.py").exists()
    assert BUILD_STAMP == ""


def test_footer_renders_build_stamp_only_when_present():
    tpl = (REPO_ROOT / "templates" / "_nexora_version.html").read_text(encoding="utf-8")
    assert "{% if nexora_build %}" in tpl
    assert "{{ nexora_build }}" in tpl
