r"""The New-report wizard's chrome: firefly layering, rail alignment, hints.

Regression guard for the second round of #336. Three faults, all cosmetic,
none of which any other test could see -- the page returned 200 and the
markup was correct every time.

1. THE FIREFLIES PAINTED OVER THE WIZARD. `#fireflyField` is `position:
   fixed; z-index: 0`, and nexora-ui.css lifts page content above it by
   promoting `<main>`. Reporting is the one page whose content is not all
   inside `<main>`: the Console shell holds the top bar, the source rail and
   the whole Simple wizard, and only the Advanced pane sits in `<main>`. So
   the dots drifted across the wizard's own text.

   Two ways to get this wrong are pinned here:

   - Giving `.firefly-field` a negative z-index instead. It looks like the
     obvious fix and it deletes the effect outright: html and body both carry
     the page background, so a negative layer paints underneath it and no dot
     is ever visible. Measured, not assumed -- with all 16 dots forced to
     opacity 1, none rendered.
   - Giving `.reporting-shell` a z-index along with its `position`. That
     makes it a stacking context, which traps the fixed panels *inside* it
     (`#rpChatPanel` at `var(--z-modal)`, z-index 61) below the sidebar.
     `position: relative` alone is enough: the shell follows `#fireflyField`
     in tree order, and equal-level positioned boxes paint in tree order.

2. THE RAIL LABEL SAT BELOW ITS NUMBER. `.rs-rail-title` carries
   `padding-top: 4px` from the original *vertical* rail, where it drops the
   label onto a 28px dot's first text line. The Console reuses the markup
   horizontally, where the chip centres dot and label against each other, so
   the padding pushed the label down inside a centred box: its text landed
   ~2.5px below the number's. Resetting it leaves 0.45px, which is nothing.

3. THE HINT HAD NO RULE AT ALL. `.reporting-simple-hint` inherited 16px body
   text in the primary colour and the global `p` reset's zero margin, so the
   line explaining the answers was louder than the answers and touched them.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSS = REPO / "static" / "css"


def _read(name: str) -> str:
    """The stylesheet with comments dropped -- they carry braces and commas."""
    raw = (CSS / name).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", " ", raw, flags=re.DOTALL)


SHARED = _read("nexora-ui.css")
REPORTING = _read("reporting.css")
CONSOLE = _read("reporting-console.css")


def _block(css: str, selector: str) -> str:
    """The declarations of the first rule whose selector list matches exactly."""
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        heads = [h.strip() for h in match.group(1).split(",") if h.strip()]
        if selector in heads:
            return match.group(2)
    raise AssertionError(f"no rule for {selector!r}")


# --- 1. the firefly backdrop ------------------------------------------------


def test_firefly_field_still_sits_at_zero_not_below_the_page_background():
    z = re.search(r"z-index:\s*(-?\d+)", _block(SHARED, ".firefly-field"))
    assert z, ".firefly-field lost its z-index"
    assert int(z.group(1)) >= 0, (
        "a negative z-index puts the dots under html/body's own background, "
        "which hides them completely -- promote the content instead"
    )


def test_reporting_shell_is_lifted_above_the_firefly_backdrop():
    block = _block(SHARED, "body.nx-app .reporting-shell")
    assert "position: relative" in block


def test_reporting_shell_creates_no_stacking_context():
    block = _block(SHARED, "body.nx-app .reporting-shell")
    assert "z-index" not in block, (
        "a z-index here traps the fixed panels inside the shell "
        "(#rpChatPanel) below the sidebar; position alone is enough"
    )


def test_main_is_still_promoted_for_every_other_page():
    assert "z-index: 1" in _block(SHARED, "body.nx-app main")


# --- 2. the wizard rail -----------------------------------------------------


def test_vertical_rail_still_pads_its_title():
    """The base rule is correct for the layout it was written for."""
    assert "padding-top: 4px" in _block(REPORTING, ".rs-rail-title")


def test_console_rail_resets_that_padding():
    block = _block(CONSOLE, "body.reporting-console .rs-rail-title")
    assert re.search(
        r"padding-top:\s*0\b", block
    ), "without this the label's text sits ~2.5px below the number's"


# --- 3. the hint under each question ----------------------------------------


def test_hint_is_quieter_than_the_answers_it_explains():
    block = _block(REPORTING, ".reporting-simple-hint")
    size = re.search(r"font-size:\s*(\d+)px", block)
    assert size and int(size.group(1)) < 16, "the hint must not inherit body size"
    assert "var(--nx-text-sec)" in block, "the hint must not use the primary colour"


def test_hint_is_set_off_from_the_answers_above_it():
    block = _block(REPORTING, ".reporting-simple-hint")
    margin = re.search(r"margin:\s*(\d+)px", block)
    assert (
        margin and int(margin.group(1)) >= 12
    ), "the hint touched the last row of chips before #336"
