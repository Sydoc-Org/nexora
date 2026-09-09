"""Permission codes follow <area>[.<object>[.<sub>]].<action>[.<scope>] (spec #238)."""

import re
from pathlib import Path

from nx_lib.security import PERMISSION_CODE_RE

ROOT = Path(__file__).resolve().parents[2]
_LITERAL = re.compile(
    r"""(?:require_permission|has_permission|require_any_permission)\(\s*['"]([^'"]+)['"]"""
)
_SEED = re.compile(r"^\s*\('([a-zA-Z0-9_.]+)',\s*'", re.M)
_MIGRATION = re.compile(r"\(N'[^']+',\s*N'([^']+)',", re.M)


def _referenced_codes():
    out = set()
    for folder, suffix in (("nx_lib", "*.py"), ("templates", "*.html")):
        for f in (ROOT / folder).rglob(suffix):
            out.update(_LITERAL.findall(f.read_text(encoding="utf-8", errors="ignore")))
    return out


def test_referenced_codes_match_the_grammar():
    bad = sorted(c for c in _referenced_codes() if not PERMISSION_CODE_RE.fullmatch(c))
    assert bad == [], bad


def test_seed_and_rename_migration_match_the_grammar():
    seed_sql = (ROOT / "sql/test/seed.sql").read_text(encoding="utf-8")
    # Only the dbo.Permission block: the seed also inserts organizations and profiles.
    block = seed_sql.split("INSERT INTO dbo.Permission", 1)[1].split("\nGO", 1)[0]
    seed = _SEED.findall(block)
    mig = _MIGRATION.findall(
        (ROOT / "sql/_migrations/NexoraDB/0088_permission_rename.sql").read_text(encoding="utf-8")
    )
    assert seed and mig
    bad = sorted(c for c in set(seed) | set(mig) if not PERMISSION_CODE_RE.fullmatch(c))
    assert bad == [], bad
