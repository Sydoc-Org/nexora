"""Single source of truth for the nexora application version.

Kept dependency-free so it can be imported from anywhere (the dev CLI, the Flask
context processor that feeds the footer, tests) without side effects. Keep this in
sync with ``pyproject.toml`` ``[project].version`` — ``tests/unit/test_version.py``
enforces that they match.
"""

__version__ = "2.5.64"
