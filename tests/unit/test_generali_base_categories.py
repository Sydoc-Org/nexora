r"""Base Services keeps its categories in the template, so guard them there.

Unlike Additional Services, which reads `dbo.EffortCategories`, the Base
Services page hardcodes its category list in
`templates/js/_generali_base_services_js.html` as two arrays:

    BASE_CATEGORIES    -- offered in the add/edit dropdowns AND the filter
    LEGACY_CATEGORIES  -- offered in the FILTER only

That split is the whole point of this test. A category that is retired has to
move from the first list to the second, never be deleted: the rows already
carrying it stay in the table and keep appearing in the month report, so if
the filter can no longer select it those hours become unreachable from the UI
while still counting in every total. Someone tidying the list a year from now
would have no way to know that from the code alone.

POE is the live case. Generali moved it to Zusatzleistungen on 2026-10-01
(migration `GeneraliDB/0016`), so it must not be bookable here any more --
but every POE hour booked up to 30 September was booked here.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARTIAL = REPO / "templates" / "js" / "_generali_base_services_js.html"


def _array(name: str) -> list[str]:
    """The string literals of a top-level `const <name> = [...]` array."""
    src = PARTIAL.read_text(encoding="utf-8")
    match = re.search(rf"const\s+{name}\s*=\s*\[(.*?)\]\s*;", src, re.S)
    assert match, f"{name} not found in {PARTIAL.name} -- did the array get renamed?"
    return re.findall(r'"([^"]+)"', match.group(1))


def test_poe_is_no_longer_bookable_in_base_services():
    """Generali books POE under Zusatzleistungen from 2026-10-01."""
    assert "POE" not in _array("BASE_CATEGORIES"), (
        "POE is offered in the Base Services add/edit dropdown again. It moved "
        "to Additional Services on 2026-10-01 (GeneraliDB/0016)."
    )


def test_poe_is_still_filterable_in_base_services():
    """The hours booked before the move must stay reachable."""
    assert "POE" in _array("LEGACY_CATEGORIES"), (
        "POE was dropped from Base Services entirely rather than retired into "
        "LEGACY_CATEGORIES. Every POE entry booked up to 2026-09-30 is still "
        "in BaseServiceEntries and still counts in the month report -- without "
        "the filter option those rows cannot be selected in the UI at all."
    )


def test_the_two_lists_do_not_overlap():
    """A category in both would render twice in the filter dropdown."""
    both = set(_array("BASE_CATEGORIES")) & set(_array("LEGACY_CATEGORIES"))
    assert not both, f"listed as both bookable and legacy: {sorted(both)}"


def test_the_remaining_bookable_categories_are_the_expected_three():
    """Not a style check -- these strings are stored verbatim in
    `BaseServiceEntries.Category` and matched by exact string, so a rename is
    a data migration, not an edit."""
    assert _array("BASE_CATEGORIES") == [
        "Physical Mailroom, AVOR & Scanning",
        "Nk1 & NK2",
        "PPR",
    ]
