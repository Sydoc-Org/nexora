"""Pre-commit nudge: Reporting behaviour changed but its help/docs did not.

Non-blocking by design (always exits 0) - it reminds, the human decides.
Wired in .pre-commit-config.yaml (reporting-help-sync): the files: filter
there decides when the hook runs at all; the staged-file check here decides
whether to print the reminder.
"""

from __future__ import annotations

import subprocess
import sys

# Files that define user-visible Reporting behaviour ...
WATCHED_PREFIXES = (
    "templates/reporting.html",
    "templates/_reporting_simple.html",
    "templates/reporting_metrics.html",
    "templates/reporting_sources.html",
    "templates/js/_reporting_",
    "static/js/reporting_",  # bodies lifted out of the partials above (#191)
    "nx_lib/views/reporting/",  # split into a package (phase 2a) - any submodule
)
# ... and the two places that document it for end users.
HELP_FILES = (
    "docs/howto/reporting-guide.md",
    "templates/_reporting_help.html",
)


def stale_help_warning(staged: list[str]) -> str | None:
    """Return the reminder text, or None when the commit looks fine."""
    touched = [f for f in staged if f.startswith(WATCHED_PREFIXES)]
    if not touched or any(f in staged for f in HELP_FILES):
        return None
    lines = "\n".join(f"  - {f}" for f in touched)
    return (
        "Reporting behaviour files are in this commit, but neither the user\n"
        "guide (docs/howto/reporting-guide.md) nor the in-app tips panel\n"
        "(templates/_reporting_help.html) changed:\n"
        f"{lines}\n"
        "If the change is user-visible, update both in the same commit\n"
        '(CLAUDE.md "Keeping docs in sync"). Refactor-only? Carry on.'
    )


def main() -> int:
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    warning = stale_help_warning(staged)
    if warning:
        print(warning)
    # ponytail: nudge only - a blocking gate would fire on every refactor
    return 0


if __name__ == "__main__":
    sys.exit(main())
