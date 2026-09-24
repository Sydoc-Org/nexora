r"""The workitem stage timeline has to follow the theme, not paint its own white.

Regression guard for #326. The stepper circles carried `background: #fff`
written straight in, with no dark counterpart, so on a dark page the running
stage rendered as a white disc. It was the worst possible glyph for it:
`fa-circle-check` is a filled disc with the tick knocked *out*, so the white
showed through the tick and the whole thing read as a bright bullseye -- the
loudest element on an otherwise dark row. Nothing failed; the page returned
200 and simply looked wrong.

The invariants are about *where the colour comes from*, not what it looks
like. A surface that sits on the themed panel must take its colour from a
token, because a token is the only thing that has a dark value. Two `#fff`
uses in the same block are legitimate and are named here so the test does not
quietly start passing for the wrong reason:

  - `.is-done { color: #fff }` -- an icon on the accent fill, white in both
    themes by design.
  - the document surfaces (`.src-thumb`, `.wi-doc-thumb`, `.wi-doc-full__page`)
    -- those are scanned pages, and paper is white in the dark too.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSS = REPO / "static" / "css"

SHEET = CSS / "workitems_overview.css"
SHARED = CSS / "nexora-ui.css"

# Selectors that sit on the themed panel and therefore must not hardcode a
# background. Every one of these was a white blob in dark mode before #326.
THEMED_SURFACES = (
    ".wi-stepper__icon",
    ".wi-stepper__icon.is-current",
    ".wi-doc-fullbtn",
    ".wi-show-sources-btn",
)

# The document column renders page images. A scanned page is white paper in
# both themes, so these keep their literal white on purpose.
PAPER_SURFACES = (".src-thumb", ".wi-doc-thumb", ".wi-doc-full__page")

WHITE = re.compile(r"#fff(?:fff)?\b|\bwhite\b", re.IGNORECASE)


def _rules(path: Path):
    """(selector, body) for every rule in the sheet, comments stripped."""
    src = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", src)]


def _declarations_for(selector: str):
    """Bodies of rules whose selector list contains exactly this selector."""
    out = []
    for sel, body in _rules(SHEET):
        parts = [p.strip() for p in sel.split(",")]
        if selector in parts:
            out.append(body)
    return out


def _background_of(body: str) -> str:
    hits = re.findall(r"(?:^|;)\s*background(?:-color)?\s*:\s*([^;]+)", body)
    return hits[-1].strip() if hits else ""


def test_the_stepper_block_still_exists():
    """If the stepper is renamed or removed, the rest of this file is vacuous
    and would pass while guarding nothing."""
    assert SHEET.exists()
    selectors = {sel for sel, _ in _rules(SHEET)}
    flat = " ".join(selectors)
    for name in THEMED_SURFACES:
        assert name in flat, f"{name} is gone -- retarget or delete this guard"


def test_themed_surfaces_take_their_background_from_a_token():
    """A hardcoded background has no dark value, which is the whole bug."""
    for selector in THEMED_SURFACES:
        bodies = _declarations_for(selector)
        assert bodies, f"no rule declares {selector}"
        backgrounds = [_background_of(b) for b in bodies if _background_of(b)]
        assert backgrounds, f"{selector} declares no background at all"
        for value in backgrounds:
            assert "var(--nx-" in value, (
                f"{selector} has background {value!r} -- must be a token, or it "
                f"cannot follow the theme (#326)"
            )
            assert not WHITE.search(
                value
            ), f"{selector} still resolves to a literal white: {value!r}"


def test_pending_stage_label_is_a_token_not_a_grey_literal():
    """`#c2c7cf` was ~1.6:1 on white -- unreadable in light mode and wrong in
    dark. The colour has to come from the text scale."""
    bodies = _declarations_for(".wi-stepper__label")
    assert bodies
    for body in bodies:
        colors = re.findall(r"(?:^|;)\s*color\s*:\s*([^;]+)", body)
        assert colors, ".wi-stepper__label declares no colour"
        for value in colors:
            assert (
                "var(--nx-" in value
            ), f".wi-stepper__label colour {value!r} must be a token (#326)"


def test_the_card_token_actually_has_a_dark_value():
    """The fix only works because --nx-card is redefined under html.dark. If
    that block ever loses the token, every surface above silently goes back to
    rendering light on a dark page."""
    src = SHARED.read_text(encoding="utf-8")
    dark = src.split("html.dark", 1)
    assert len(dark) == 2, "nexora-ui.css has no html.dark block"
    block = dark[1].split("}", 1)[0]
    for token in ("--nx-card:", "--nx-text-meta:"):
        assert token in block, f"{token} is not redefined for dark mode"


def test_document_surfaces_keep_their_white_on_purpose():
    """Guard against an over-eager sweep: these are page images, and paper is
    white in both themes. If someone tokenises them, scans get a dark backing
    and the page content stops reading as a document."""
    for selector in PAPER_SURFACES:
        bodies = [b for sel, b in _rules(SHEET) if selector in sel]
        assert bodies, f"{selector} is gone -- update this guard"
        assert any(WHITE.search(_background_of(b)) for b in bodies), (
            f"{selector} no longer has a white background; page images are "
            f"meant to look like paper in both themes"
        )


def test_the_done_icon_keeps_its_white_glyph():
    """`.is-done` puts the icon on the accent fill, where white is correct in
    both themes -- it is a foreground colour, not a surface."""
    bodies = _declarations_for(".wi-stepper__icon.is-done")
    assert bodies
    assert any(
        WHITE.search(m)
        for body in bodies
        for m in re.findall(r"(?:^|;)\s*color\s*:\s*([^;]+)", body)
    ), ".is-done lost its white icon colour"
