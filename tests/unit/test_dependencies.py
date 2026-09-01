"""Every third-party module the app imports must be declared in pyproject.toml.

The generated requirements*.txt files come from uv.lock, which comes from
pyproject.toml. A dep hand-added to requirements.txt only (as pypdfium2,
matplotlib and markdown-it-py once were) is invisible to `uv sync`, so every
fresh checkout gets ModuleNotFoundError while the machine that added it keeps
working off ad-hoc global installs.
"""

import ast
import pathlib
import re
import sys
import tomllib

REPO = pathlib.Path(__file__).resolve().parents[2]

# ponytail: hand-written map instead of importlib.metadata lookups — it only
# needs the handful of packages whose import name differs from the dist name.
IMPORT_TO_DIST = {
    "PIL": "pillow",
    "dotenv": "python-dotenv",
    "magic": "python-magic-bin",
    "markdown_it": "markdown-it-py",
    "psycopg2": "psycopg2-binary",
}

# "scripts" joined the list when scripts/test_db_reset.py started importing
# scripts/db_lock.py -- it is a directory in this repo, not a PyPI package,
# so it can never appear in pyproject.toml.
FIRST_PARTY = {"nx_lib", "nx_main", "tests", "conftest", "scripts"}


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def _declared() -> set[str]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    specs = list(data["project"]["dependencies"])
    for group in data.get("dependency-groups", {}).values():
        specs.extend(s for s in group if isinstance(s, str))  # skip include-group tables
    # keep the name only: "coverage[toml]==7.6.10" / "sqlglot>=30.8.0" -> name
    return {_normalize(re.split(r"[<>=!~\[;\s]", s, maxsplit=1)[0]) for s in specs}


def _imported(paths: list[pathlib.Path]) -> set[str]:
    files: list[pathlib.Path] = []
    for p in paths:
        files.extend([p] if p.is_file() else p.rglob("*.py"))

    mods: set[str] = set()
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods.add(node.module.split(".")[0])
    return {m for m in mods if m not in sys.stdlib_module_names and m not in FIRST_PARTY}


def test_runtime_imports_are_declared():
    """nx_lib/ + nx_main.py may only import declared packages."""
    imported = _imported([REPO / "nx_lib", REPO / "nx_main.py"])
    missing = {m for m in imported if _normalize(IMPORT_TO_DIST.get(m, m)) not in _declared()}
    assert not missing, (
        f"imported by the app but missing from pyproject.toml: {sorted(missing)}. "
        "Add them to [project].dependencies and regenerate requirements*.txt "
        "(see CONTRIBUTING.md) — editing requirements.txt by hand does nothing "
        "for `uv sync`."
    )


def test_script_imports_are_declared():
    """scripts/ and ops/ may only import declared packages (runtime or dev)."""
    imported = _imported([REPO / "scripts", REPO / "ops"])
    missing = {m for m in imported if _normalize(IMPORT_TO_DIST.get(m, m)) not in _declared()}
    assert (
        not missing
    ), f"imported by scripts/ or ops/ but missing from pyproject.toml: {sorted(missing)}"
