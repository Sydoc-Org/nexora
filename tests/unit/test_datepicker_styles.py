r"""The date-picker styling has to reach every page that opens a calendar.

This is a regression guard for a bug that shipped: the flatpickr overrides
lived in static/css/dashboard.css, which only two templates load, while
eleven templates open a calendar. Ten of them rendered the vanilla
light-only CDN calendar on a dark page, and nothing failed -- the pages
returned 200 and the styles were simply absent.

So the invariants worth pinning are structural, not visual: the rules live
in the globally loaded sheet, no page-scoped sheet takes them back, every
consumer actually loads that sheet, and the selectors beat flatpickr's own
without depending on link order.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSS = REPO / "static" / "css"
TEMPLATES = REPO / "templates"

SHARED = CSS / "nexora-ui.css"
FLATPICKR_CDN = "flatpickr@4.6.13/dist/flatpickr.min.css"


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def _pages_loading_flatpickr():
    return [p for p in _templates() if FLATPICKR_CDN in p.read_text(encoding="utf-8")]


def _flatpickr_rule_lines(path: Path):
    """Selector lines mentioning flatpickr, excluding comments."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if "flatpickr" not in s or s.startswith(("/*", "*", "//")):
            continue
        if "{" in s or s.endswith(","):
            out.append(s)
    return out


def test_the_rules_live_in_the_globally_loaded_sheet():
    assert _flatpickr_rule_lines(SHARED), "nexora-ui.css carries no flatpickr rules"


def test_no_page_scoped_stylesheet_takes_the_rules_back():
    """dashboard.css is the one that caused this; check every page sheet, so a
    future copy into reporting.css or admin.css fails here too."""
    offenders = {
        p.name: _flatpickr_rule_lines(p)
        for p in sorted(CSS.glob("*.css"))
        if p != SHARED and _flatpickr_rule_lines(p)
    }
    assert not offenders, (
        "flatpickr rules in a page-scoped stylesheet -- pages that do not load "
        f"it get the light-only calendar: {offenders}"
    )


def test_every_page_that_opens_a_calendar_loads_the_shared_sheet():
    pages = _pages_loading_flatpickr()
    assert pages, "no template loads flatpickr -- has the CDN pin changed?"
    missing = []
    for p in pages:
        text = p.read_text(encoding="utf-8")
        # Either linked directly or inherited from the shared header.
        if "nexora-ui.css" not in text and "_header.html" not in text:
            missing.append(str(p.relative_to(REPO)))
    assert not missing, f"these load flatpickr but never nexora-ui.css: {missing}"


def test_selectors_do_not_depend_on_link_order():
    """The pages link nexora-ui.css in <head> BEFORE the flatpickr CDN sheet,
    so an equal-specificity rule loses. Every rule must carry `html` (or
    `html.dark`) to sit strictly above flatpickr's own."""
    bad = [s for s in _flatpickr_rule_lines(SHARED) if not s.startswith("html")]
    assert not bad, "unprefixed flatpickr selectors lose to the CDN sheet on load order: " f"{bad}"


def test_colours_come_from_tokens_not_hardcoded_hexes():
    """The original base block pinned `color: #111827`, which is the only
    reason a separate dark override had to exist. Shadows stay rgba()."""
    section = SHARED.read_text(encoding="utf-8")
    start = section.index("11. DATE PICKER")
    body = section[start:]
    hexes = re.findall(r":\s*(#[0-9a-fA-F]{3,6})\b", body)
    # The var() fallbacks are allowed -- they only apply if the token is unset.
    allowed = set(re.findall(r"var\(--nx-[a-z-]+,\s*(#[0-9a-fA-F]{3,6})\)", body))
    assert not (set(hexes) - allowed), (
        "hardcoded colours in the date-picker section; use --nx-* tokens so "
        f"both modes derive from them: {sorted(set(hexes) - allowed)}"
    )


def test_a_page_that_never_opens_a_calendar_does_not_ship_the_library():
    """dashboard.html loaded the CDN pair and never called flatpickr."""
    text = (TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    assert FLATPICKR_CDN not in text, "dashboard.html loads flatpickr but never uses it"
