"""The pre-push branch-name guard's regex, checked without invoking PowerShell.

The pattern is the contract between CONTRIBUTING.md and every developer's
`git push`; getting it wrong either blocks legitimate work or lets the old
long-lived version branches back in. Read it out of the script rather than
duplicating it here, so a change to one fails the other.

`-match` in PowerShell is case-insensitive, hence IGNORECASE below.
"""

import re
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "git-hooks" / "branch-name-guard.ps1"


def _allowed_pattern() -> re.Pattern[str]:
    line = next(
        ln for ln in GUARD.read_text(encoding="utf-8").splitlines() if ln.startswith("$allowed")
    )
    return re.compile(line.split("'", 2)[1], re.IGNORECASE)


@pytest.mark.parametrize(
    "branch",
    [
        "fix/253-collab-rules",
        "feat/241-dashboard-overwork",
        "docs/nx-cli-reference",
        "chore/bump-uv",
        "refactor/workitems-query",
        "test/e2e-flake",
        "ci/deploy-timeout",
        "v3.1",  # legacy cycle branch, still in flight
        "v3.2.4.1",
        "feature/3.0.9",  # pre-3.1 naming
    ],
)
def test_accepts(branch: str) -> None:
    assert _allowed_pattern().match(branch), f"{branch} should push"


@pytest.mark.parametrize(
    "branch",
    [
        "main",  # PRs only; the script also refuses it by name, with its own message
        "hotfix/urgent",  # not a Conventional-Commit type
        "wip",
        "fix/",  # empty slug
        "fix/Has Spaces",
        "feat/foo/bar",  # one level only
        "v3",  # needs at least x.y
        "3.2.5",
    ],
)
def test_refuses(branch: str) -> None:
    assert not _allowed_pattern().match(branch), f"{branch} should be refused"


def test_main_is_refused_by_name_with_its_own_message() -> None:
    """The regex alone would give the generic "must be <type>/<slug>" advice."""
    body = GUARD.read_text(encoding="utf-8")
    assert "if ($branch -eq 'main')" in body
    assert "nothing is pushed to 'main' directly" in body
