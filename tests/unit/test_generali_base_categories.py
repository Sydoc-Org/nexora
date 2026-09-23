r"""POE moves out of Basisleistungen on its own date, not on a deploy date.

Generali books POE under Zusatzleistungen from 2026-10-01 (migration
`GeneraliDB/0016` adds it to that catalogue). The Base Services half of the
move is here, and it is driven by `POE_CUTOVER` rather than by choosing the
right day to release: both kinds of timing mistake cost real work — ship early
and nobody can book their September hours, ship late and nobody can book their
October ones.

Unlike Additional Services, which reads `dbo.EffortCategories`, Base Services
hardcodes its category list in `templates/js/_generali_base_services_js.html`
as two arrays:

    BASE_CATEGORIES    -- offered in the add/edit dropdowns AND the filter
    LEGACY_CATEGORIES  -- offered in the FILTER only

That split is what makes the move safe. A retired category has to end up in
the second list, never be deleted: the rows already carrying it stay in
`BaseServiceEntries` and keep counting in the month report, so if the filter
could no longer select it those hours would be unreachable from the UI while
still showing up in every total. Nothing in the code says that out loud, which
is why it is written down here.
"""

import re
from datetime import date
from pathlib import Path

from nx_lib.views.generali.baseservices import POE_CUTOVER, poe_has_moved

REPO = Path(__file__).resolve().parents[2]
PARTIAL = REPO / "templates" / "js" / "_generali_base_services_js.html"


def _array(name: str) -> str:
    """The raw source of a `const <name> = [...]` array, Jinja and all."""
    src = PARTIAL.read_text(encoding="utf-8")
    match = re.search(rf"const\s+{name}\s*=\s*\[(.*?)\]\s*;", src, re.S)
    assert match, f"{name} not found in {PARTIAL.name} -- did the array get renamed?"
    return match.group(1)


# ------------------------------------------------------------- the cut-over --


def test_the_cutover_is_the_first_of_october():
    assert date(2026, 10, 1) == POE_CUTOVER


def test_poe_is_still_bookable_the_day_before():
    assert poe_has_moved(date(2026, 9, 30)) is False


def test_poe_has_moved_on_the_day_itself():
    """Boundary, not a day either side: `>=`, not `>`."""
    assert poe_has_moved(date(2026, 10, 1)) is True


def test_poe_stays_moved_afterwards():
    assert poe_has_moved(date(2027, 3, 14)) is True


# ------------------------------------------------------ the rendered lists --


def test_poe_is_offered_for_booking_only_before_the_cutover():
    """It sits behind `{% if not poe_moved %}`, so it disappears by itself."""
    base = _array("BASE_CATEGORIES")
    assert '"POE"' in base, "POE is no longer bookable at all in Base Services"
    assert "poe_moved" in base, (
        "POE is hardcoded in BASE_CATEGORIES again -- it must be gated on "
        "poe_moved, or it will still be bookable after the cut-over"
    )


def test_poe_becomes_filterable_after_the_cutover():
    """Every POE hour booked up to 30 September was booked here."""
    legacy = _array("LEGACY_CATEGORIES")
    assert '"POE"' in legacy and "poe_moved" in legacy, (
        "POE must move into LEGACY_CATEGORIES at the cut-over. Dropping it "
        "instead would leave every entry booked before the move unselectable "
        "in the filter, while those rows keep counting in the month report."
    )


def test_the_legacy_combined_category_is_always_filterable():
    """ "POE / PPR" predates all of this and is not part of the move."""
    assert '"POE / PPR"' in _array("LEGACY_CATEGORIES")


def test_poe_is_never_in_both_lists_at_once():
    """Listed twice, it would render twice in the filter dropdown.

    The two gates must be opposites: `{% if not poe_moved %}` for booking and
    `{% if poe_moved %}` for the legacy list.
    """
    base, legacy = _array("BASE_CATEGORIES"), _array("LEGACY_CATEGORIES")
    assert "if not poe_moved" in base, base
    assert re.search(r"\{%\s*if\s+poe_moved\s*%\}", legacy), legacy


def test_the_permanently_bookable_categories_are_unchanged():
    """These strings are stored verbatim in `BaseServiceEntries.Category` and
    matched by exact string, so a rename is a data migration, not an edit."""
    base = _array("BASE_CATEGORIES")
    for name in ("Physical Mailroom, AVOR & Scanning", "Nk1 & NK2", "PPR"):
        assert f'"{name}"' in base, name
