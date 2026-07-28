"""Single source of truth for the nexora application version.

Kept dependency-free so it can be imported from anywhere (the dev CLI, the Flask
context processor that feeds the footer, tests) without side effects. Keep this in
sync with ``pyproject.toml`` ``[project].version`` — ``tests/unit/test_version.py``
enforces that they match.
"""

__version__ = "2.5.65"

try:
    # ponytail: nx_lib/_build.py is written by .github/workflows/deploy.yml right
    # after the robocopy mirror ("<short-sha> · <UTC date>"). It never exists in
    # git, so dev/INT/tests fall through to "" and render version-only.
    from ._build import BUILD_STAMP
except ImportError:
    BUILD_STAMP = ""
