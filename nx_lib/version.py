"""Single source of truth for the nexora application version.

Kept dependency-free so it can be imported from anywhere (the dev CLI, the Flask
context processor that feeds the footer, tests) without side effects.

Bumping a release means editing this file and ``pyproject.toml``, then running
``uv lock``. The duplication is forced, not sloppiness: uv rejects a ``[project]``
table whose version is neither static nor supplied by a build backend, and nexora
is a virtual project that is never built or installed. ``tests/unit/test_version.py``
enforces that all three copies agree.
"""

# ponytail: bare "3.1" here — PEP 440 strips a leading "v", so the display "v"
# lives in the two templates that render it, not in the version string.
__version__ = "3.1.1"

try:
    # ponytail: nx_lib/_build.py is written by .github/workflows/deploy.yml right
    # after the robocopy mirror ("<short-sha> · <UTC date>"). It never exists in
    # git, so dev/INT/tests fall through to "" and render version-only.
    from ._build import BUILD_STAMP
except ImportError:
    BUILD_STAMP = ""
