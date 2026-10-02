r"""The safe-area insets are read through tokens, never `env()` at the use site.

`env(safe-area-inset-*)` is how a page keeps content out from under the notch
and the home indicator. It has one property that makes it uniquely awkward to
work on: **it cannot be overridden.** Setting it from a stylesheet or the
console does nothing, and every desktop browser's device emulation reports 0
for all four edges. A real iPhone reports roughly 59px at the top and 34px at
the bottom, so any layout bug living in that band is invisible outside the
physical phone -- which is exactly what happened: three symptoms reported from
the owner's iPhone could not be reproduced here at all.

Read through a custom property the same values *can* be set, so the phone's
geometry is reproducible in a desktop browser and in the Playwright suite.
That is what `scripts/phone-sweep.py` drives, and it is the only reason these
tokens exist -- the drift argument (one knob instead of sixteen hand-copied
calls, as `--nx-tabbar-h` already does for the tab bar's height) is the
smaller half of it.

Two invariants, and the second is the subtle one:

  - No stylesheet outside `nexora-ui.css` calls `env(safe-area-inset-*)`
    directly. One such call is a hole the sweep cannot see through.
  - Every token carries a `0px` fallback. A bare `env()` is invalid where the
    function is unsupported, and an invalid custom property does **not** fall
    back to zero -- it makes every `var()` reading it collapse to the
    guaranteed-invalid value, so the declaration is dropped entirely. Without
    the fallback a browser lacking `env()` would lose the padding rather than
    merely lose the inset.

Comments are stripped as whole blocks before matching, not line by line: this
file's own prose names `env(safe-area-inset-*)` repeatedly, and so does the
token block in `nexora-ui.css`. A line-oriented comment filter would read
that prose as CSS and fail the build -- the same trap that
`test_datepicker_styles.py` fell into once already.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSS = REPO / "static" / "css"
SHARED = CSS / "nexora-ui.css"

EDGES = ("top", "bottom", "left", "right")

# `/* ... */` spanning any number of lines, non-greedy.
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _rules(path: Path) -> str:
    """The sheet with every comment block removed, so only real CSS is left."""
    return _COMMENT.sub("", path.read_text(encoding="utf-8"))


def _sheets() -> list[Path]:
    return sorted(p for p in CSS.rglob("*.css") if p.name != SHARED.name)


def test_tokens_are_defined_with_a_zero_fallback():
    """`nexora-ui.css` defines one token per edge, each falling back to 0px."""
    rules = _rules(SHARED)
    for edge in EDGES:
        pattern = re.compile(
            r"--nx-sa-" + edge + r"\s*:\s*env\(\s*safe-area-inset-" + edge + r"\s*,\s*0px\s*\)"
        )
        assert pattern.search(rules), (
            f"--nx-sa-{edge} must be defined in nexora-ui.css as "
            f"env(safe-area-inset-{edge}, 0px). The 0px fallback is not "
            f"decoration: without it the token is invalid where env() is "
            f"unsupported, and every var(--nx-sa-{edge}) is then dropped "
            f"rather than treated as zero."
        )


def test_no_sheet_calls_env_safe_area_directly():
    """Only the token definitions may name `env(safe-area-inset-*)`."""
    direct = re.compile(r"env\(\s*safe-area-inset-")
    offenders = []
    for sheet in _sheets():
        for match in direct.finditer(_rules(sheet)):
            line = _rules(sheet).count("\n", 0, match.start()) + 1
            offenders.append(f"{sheet.relative_to(REPO)} (rule line ~{line})")
    assert not offenders, (
        "These sheets read the safe-area insets directly:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse var(--nx-sa-top / -bottom / -left / -right) instead. A direct "
        "env() call cannot be overridden, so the inset it guards reads 0 in "
        "every emulator and the layout there can only be checked on a physical "
        "iPhone."
    )


def test_the_tokens_are_actually_used():
    """Guard against the tokens being defined and then quietly abandoned."""
    users = {
        sheet.relative_to(REPO).as_posix() for sheet in _sheets() if "var(--nx-sa-" in _rules(sheet)
    }
    assert users, (
        "No stylesheet reads var(--nx-sa-*). Either the phone layout lost its "
        "safe-area handling, or the use sites went back to calling env() "
        "directly (which the companion test would also catch)."
    )
