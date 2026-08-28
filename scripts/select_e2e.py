"""Run only the e2e specs the outgoing push can actually affect (#223).

The pre-push gate used to run all ~228 Playwright tests on every push, adding
~12 minutes to a ~5 minute fast tier. Most of that was spent on browsers that
the diff could not possibly touch: a CSS-only change to one page still ran the
whole reporting suite.

This selects specs from the changed files instead. The full tier still runs in
CI (`test` job in .github/workflows/deploy.yml, which `deploy` needs), so
nothing reaches PROD unexercised -- this only shortens the local push.

Design rule: **fail towards running more, never less.** Anything unrecognised,
any shared file, and any error at all falls back to the entire tier, so the
worst case is a slow push rather than a missed regression.

Usage (pre-commit pre-push hook):
    python scripts/select_e2e.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
E2E_DIR = REPO_ROOT / "tests" / "e2e"

# (regex over the repo-relative path, specs it implies).
#
# Ordered: the first match wins, so put narrow rules above broad ones. Paths use
# forward slashes -- normalised below, since git reports them that way but
# Windows callers may not.
RULES: list[tuple[str, tuple[str, ...]]] = [
    # --- shared chrome: affects every page, so run everything -------------
    (r"^templates/_header\.html$", ()),
    (r"^templates/_theme_prepaint\.html$", ()),
    (r"^templates/js/_header_js\.html$", ()),
    (r"^static/css/(nexora-ui|_header|admin-tokens)\.css$", ()),
    (r"^nx_lib/(hooks|security|__init__|config|middleware)\.py$", ()),
    (r"^tests/e2e/conftest\.py$", ()),
    (r"^tests/conftest\.py$", ()),
    (r"^sql/test/", ()),
    # --- feature areas ----------------------------------------------------
    (
        r"^(nx_lib/reporting/|nx_lib/views/reporting\.py|templates/reporting|"
        r"templates/_reporting|templates/js/_reporting|static/css/reporting\.css)",
        ("test_reporting*.py",),
    ),
    (
        r"^(nx_lib/views/workitems\.py|nx_lib/(workitem_sources|octo|field_locations|"
        r"table_locations|prepared_documents)\.py|templates/workitems|"
        r"templates/js/_workitem|templates/prepared_documents\.html|"
        r"static/css/(workitems_overview|source-highlight)\.css)",
        ("test_workitems.py", "test_workitem_*.py"),
    ),
    (
        r"^(nx_lib/views/admin\.py|templates/admin/|templates/js/admin/)",
        ("test_admin.py",),
    ),
    (
        r"^(nx_lib/views/auth\.py|templates/(index|forgot_password|reset_password|"
        r"set_password|init_reset|init_2FA)\.html|static/css/auth\.css)",
        ("test_auth_pages.py", "test_login_smoke.py"),
    ),
    (
        r"^(nx_lib/views/profile\.py|nx_lib/ui_prefs\.py|templates/(profile|appearance|"
        r"feedback|whats_new)\.html|static/css/(profile|appearance|feedback)\.css)",
        ("test_profile.py",),
    ),
    (
        r"^(nx_lib/views/dashboard\.py|templates/dashboard\.html|"
        r"templates/js/_dashboard_js\.html|static/css/dashboard\.css)",
        ("test_dashboard.py",),
    ),
    # --- changes that cannot affect the browser at all ---------------------
    (r"^(docs/|README\.md|CHANGELOG\.md|CONTRIBUTING\.md|CLAUDE\.md)", None),
    (r"^\.claude/", None),
    (r"^(ops/|scripts/)", None),
    (r"^tests/(unit|integration)/", None),
    (r"^sql/_migrations/", None),
]

RUN_ALL = "run-all"
SKIP = "skip"


def changed_files() -> list[str] | None:
    """Repo-relative paths this push would publish, or None if undeterminable.

    Compares against the tracked upstream. A branch with no upstream (the first
    push of a new branch) has nothing to diff against, so we return None and the
    caller runs everything.
    """
    try:
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        if upstream.returncode != 0 or not upstream.stdout.strip():
            return None
        diff = subprocess.run(
            ["git", "diff", "--name-only", f"{upstream.stdout.strip()}...HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        if diff.returncode != 0:
            return None
        return [p.strip().replace("\\", "/") for p in diff.stdout.splitlines() if p.strip()]
    except Exception:
        return None


def select(paths: list[str]) -> set[str] | str:
    """RUN_ALL, SKIP, or the set of spec globs to run."""
    specs: set[str] = set()
    for path in paths:
        for pattern, targets in RULES:
            if re.search(pattern, path):
                if targets == ():  # shared: everything
                    return RUN_ALL
                if targets is None:  # cannot affect the browser
                    break
                specs.update(targets)
                break
        else:
            # Unrecognised path -- be conservative.
            return RUN_ALL
    return specs or SKIP


def expand(globs: set[str]) -> list[str]:
    out: set[Path] = set()
    for g in globs:
        out.update(E2E_DIR.glob(g))
    return sorted(str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in out)


def main() -> int:
    paths = changed_files()
    if paths is None:
        print("[e2e] could not determine the diff -- running the full e2e tier")
        return run(["tests/e2e"])
    if not paths:
        print("[e2e] no changed files vs upstream -- running the full e2e tier")
        return run(["tests/e2e"])

    choice = select(paths)
    if choice == RUN_ALL:
        print(
            f"[e2e] {len(paths)} changed file(s) include shared or unmapped paths "
            "-- running the full e2e tier"
        )
        return run(["tests/e2e"])
    if choice == SKIP:
        print(f"[e2e] {len(paths)} changed file(s), none browser-facing -- skipping e2e")
        print("[e2e] the full tier still runs in CI before deploy")
        return 0

    targets = expand(choice)
    if not targets:
        print("[e2e] mapping produced no existing spec -- running the full e2e tier")
        return run(["tests/e2e"])
    print(f"[e2e] {len(paths)} changed file(s) -> {len(targets)} spec(s):")
    for t in targets:
        print(f"[e2e]   {t}")
    return run(targets)


def run(targets: list[str]) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *targets], cwd=REPO_ROOT, check=False
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
