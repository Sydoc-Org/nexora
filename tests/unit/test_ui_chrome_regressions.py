"""Static guards for the shared UI chrome: search field, scope picker, sidebar
rail, theme pre-paint and the reporting chat panel.

Each invariant here exists because the chrome broke in a way no route test
could see -- the markup was valid, the page rendered, and only the geometry or
the cascade was wrong. Stating them as invariants keeps a later "tidy the CSS"
pass from silently undoing the fix.

These are deliberately static (read the template/CSS, assert on the text)
rather than browser tests: they run in the fast tier on every push, and the
values they pin -- padding pairs, an explicit box size, a reserved width -- are
exactly the ones a refactor drops by accident. The e2e counterparts in
tests/e2e/test_ui_chrome_regressions.py prove the same properties actually hold
in a real layout.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"
CSS = REPO_ROOT / "static" / "css"

# Tailwind spacing scale -> rem, for the handful of steps the search field uses.
_SPACING_REM = {"3": 0.75, "3.5": 0.875, "10": 2.5}
_PX_REM = 1 / 16  # workitems_overview.css's .nx-wi-search uses plain px, not Tailwind steps.


def _rule_body(css_text, selector):
    """Return the declaration block for `selector`, or None.

    Matches the selector only when it stands alone in the selector list (the
    files here never group these particular selectors), so a longer selector
    that merely contains the same substring cannot be picked up by mistake.
    """
    pattern = re.compile(
        r"(?:^|[}\n])\s*" + re.escape(selector) + r"\s*\{([^}]*)\}",
        re.MULTILINE,
    )
    match = pattern.search(css_text)
    return match.group(1) if match else None


def _declaration(block, prop):
    """Return the value of `prop` in a declaration block, or None."""
    match = re.search(r"(?:^|;)\s*" + re.escape(prop) + r"\s*:\s*([^;]+)", block)
    return match.group(1).strip() if match else None


# --------------------------------------------------------------------------
# Workitems search field: the icon sits inside the input's own padding
# --------------------------------------------------------------------------


def _search_field_markup():
    text = (TEMPLATES / "workitems_overview.html").read_text(encoding="utf-8")
    # The icon <i> and the input live inside the same .nx-wi-search wrapper
    # (#299 console redesign); grab that slice so the assertions below cannot
    # accidentally read another field's classes.
    start = text.index('<div class="nx-wi-search"')
    end = text.index('data-testid="workitems-search"', start)
    return text[start:end]


def _search_field_css_rule(prop):
    css_text = (CSS / "workitems_overview.css").read_text(encoding="utf-8")
    block = _rule_body(css_text, ".nx-wi-search i")
    assert block is not None, ".nx-wi-search i rule disappeared from workitems_overview.css"
    value = _declaration(block, prop)
    assert value is not None, f".nx-wi-search i lost its {prop} declaration"
    return value


def test_workitems_search_icon_fits_inside_the_input_padding():
    """The magnifier is absolutely positioned over the input, so the input's
    left padding has to clear the icon's left offset plus the glyph itself.
    When they were both set from the same 'looks about right' guess the glyph
    and the placeholder overlapped."""
    icon_left = float(_search_field_css_rule("left").rstrip("px")) * _PX_REM

    css_text = (CSS / "workitems_overview.css").read_text(encoding="utf-8")
    input_block = _rule_body(css_text, ".nx-wi-search .nx-input")
    assert (
        input_block is not None
    ), ".nx-wi-search .nx-input rule disappeared from workitems_overview.css"
    input_pad = _declaration(input_block, "padding-left")
    assert input_pad is not None, ".nx-wi-search .nx-input lost its padding-left"
    input_rem = float(input_pad.rstrip("px")) * _PX_REM

    # A 10px (~0.625rem) glyph plus a little air. If the input's padding
    # stops short of that, text starts underneath the icon.
    assert input_rem >= icon_left + 0.625, (
        f"input padding-left ({input_rem}rem) does not clear the icon "
        f"(offset {icon_left}rem + ~0.625rem glyph); the placeholder will "
        f"render under the magnifier."
    )


def test_workitems_search_icon_does_not_swallow_clicks():
    """The icon overlays the input's click target. Without pointer-events:none
    a click on the glyph does not focus the field."""
    assert (
        _search_field_css_rule("pointer-events") == "none"
    ), "the search magnifier lost pointer-events:none; clicking it no longer focuses the input"


# --------------------------------------------------------------------------
# Process scope picker: the checkbox needs an explicit box
# --------------------------------------------------------------------------


def test_scope_picker_checkbox_has_an_explicit_size():
    """nexora-ui.css draws its own checkbox chrome with appearance:none, which
    drops the widget's intrinsic size. There is now a global 16px floor (see
    test_checkbox_chrome_has_a_global_size_floor), but the scope picker asks
    for 18px on purpose: rows are built in JS with no utility classes, and at
    the floor size every process read as an unlabelled dot -- selected and
    unselected became indistinguishable (issue #206)."""
    block = _rule_body((CSS / "nexora-ui.css").read_text(encoding="utf-8"), ".nx-scope-row input")
    assert block is not None, ".nx-scope-row input rule disappeared from nexora-ui.css"

    for prop in ("width", "height"):
        value = _declaration(block, prop)
        assert value is not None, (
            f".nx-scope-row input has no explicit {prop}; appearance:none "
            f"checkboxes collapse without one (issue #206)"
        )
        pixels = float(re.match(r"([\d.]+)px", value).group(1))
        assert pixels >= 14, f"{prop} of {value} is too small to read as a checkbox"


def test_checkbox_chrome_has_a_global_size_floor():
    """appearance:none takes the widget's intrinsic size with it, so any
    checkbox or radio that does not size itself renders as a ~2px speck. That
    was 15 of them (reporting's forecast + share controls, the admin
    clients/tenants/maintenance modals, user_detail's override radios) before
    the base rule grew a floor. min-* rather than width/height on purpose:
    Tailwind's h-4/w-4 sit in @layer utilities and lose to this unlayered
    file, so a hard size here would override every caller."""
    css = (CSS / "nexora-ui.css").read_text(encoding="utf-8")
    match = re.search(
        r'body\.nx-app input\[type="checkbox"\],\s*'
        r'body\.nx-app input\[type="radio"\]\s*\{([^}]*)\}',
        css,
    )
    assert match, "the shared checkbox/radio chrome rule is gone"
    # The block carries a long comment; drop it so a commented-out
    # declaration cannot satisfy the assertions below.
    block = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)
    for prop in ("min-width", "min-height"):
        value = _declaration(block, prop)
        assert value is not None, (
            f"the checkbox/radio chrome lost its {prop} floor; unsized "
            f"checkboxes collapse to an invisible speck again"
        )
        assert (
            float(re.match(r"([\d.]+)px", value).group(1)) >= 14
        ), f"{prop} of {value} is too small to read as a checkbox"


def test_hidden_switch_inputs_opt_out_of_the_floor():
    """Counterpart guard. .ml-toggle replaces the input with a slider span and
    collapses the input itself; the global floor would re-inflate it to 16px
    inside a 36x20 label, so the opt-out has to out-specify the base rule --
    body.nx-app input[type=checkbox] and body.nx-app .ml-toggle input tie, and
    nexora-ui.css loads last."""
    block = _rule_body(
        (CSS / "admin.css").read_text(encoding="utf-8"),
        'body.nx-app label.ml-toggle input[type="checkbox"]',
    )
    assert block is not None, ".ml-toggle's input opt-out is gone from admin.css"
    for prop in ("min-width", "min-height"):
        assert _declaration(block, prop) == "0", (
            f".ml-toggle input does not reset {prop}; the global floor will "
            f"give the hidden input a 16px box inside the 36x20 switch"
        )


# --------------------------------------------------------------------------
# Sidebar rail: an expanded sidebar must not cover the page
# --------------------------------------------------------------------------


def test_sidebar_hover_reserves_the_expanded_width():
    """Unpinned, the rail is 64px and `body` reserves 100px for it. Hovering
    expands it to 220px -- which used to paint straight over the page, because
    only the *pinned* state widened body's padding. The hover rule has to
    reserve the same width the sidebar expands to."""
    text = (CSS / "_header.css").read_text(encoding="utf-8")

    expanded = _declaration(_rule_body(text, "html.sidebar-pinned #nexora-sidebar"), "width")
    hover_block = _rule_body(text, "body:has(#nexora-sidebar:hover)")
    assert hover_block is not None, (
        "body:has(#nexora-sidebar:hover) is gone; an unpinned sidebar paints "
        "over the page again when hovered"
    )
    reserved = _declaration(hover_block, "padding-left")
    assert reserved == expanded, (
        f"hover reserves {reserved} but the sidebar expands to {expanded}; "
        f"the difference is page content the sidebar covers"
    )


def test_mobile_still_drops_the_sidebar_padding():
    """The narrow-viewport override collapses the rail to an off-canvas drawer
    and zeroes body's padding with !important. The hover rule must not be
    strong enough to fight it -- an !important there would strand a 220px
    gutter on phones."""
    hover_block = _rule_body(
        (CSS / "_header.css").read_text(encoding="utf-8"), "body:has(#nexora-sidebar:hover)"
    )
    assert "!important" not in hover_block, (
        "the sidebar hover rule uses !important and will override the mobile "
        "padding-left: 0 reset"
    )


# --------------------------------------------------------------------------
# Reporting chat panel
# --------------------------------------------------------------------------


def test_chat_panel_is_non_modal():
    """Issue #205: the chat is a floating tool window, not a dialog that owns
    the page. A backdrop would dim the report underneath and swallow clicks on
    it, which defeats the point of being able to drag the panel out of the way
    -- you would have to close it to use whatever you moved it away from."""
    markup = (TEMPLATES / "reporting.html").read_text(encoding="utf-8")
    css = (CSS / "reporting.css").read_text(encoding="utf-8")
    js = (TEMPLATES / "js" / "_reporting_ai_js.html").read_text(encoding="utf-8")

    assert "rpChatBackdrop" not in markup, "the chat backdrop element is back in reporting.html"
    assert "rpChatBackdrop" not in js, "the chat JS still wires a backdrop"
    assert _rule_body(css, ".reporting-chat-backdrop") is None, (
        ".reporting-chat-backdrop is back in reporting.css; the page will be "
        "dimmed and unusable while the chat is open"
    )
    assert 'aria-modal="false"' in markup, (
        "the chat panel does not declare aria-modal=false; assistive tech will "
        "announce it as modal and hide the rest of the page"
    )


def test_drill_drawer_is_still_modal():
    """Counterpart guard. Only the *chat* went non-modal -- the drill-through
    drawer is a different interaction (drill into a number, read, dismiss) and
    keeps its backdrop. Stripping both would be over-applying the change, and
    the chat's openPanel() closes the drill precisely because the drill still
    dims the page."""
    markup = (TEMPLATES / "reporting.html").read_text(encoding="utf-8")
    css = (CSS / "reporting.css").read_text(encoding="utf-8")

    assert "rdBackdrop" in markup, "the drill drawer lost its backdrop"
    assert _rule_body(css, ".reporting-drill-backdrop") is not None


def test_clicking_the_page_does_not_close_the_chat():
    """With no backdrop there is nothing to click "outside" onto, so a
    document-level click handler that closes the panel would make the page
    unusable in a subtler way: every click on the report would dismiss the
    chat."""
    js = (TEMPLATES / "js" / "_reporting_ai_js.html").read_text(encoding="utf-8")
    assert not re.search(r"document\.addEventListener\(\s*[\"']click[\"']", js), (
        "the chat JS registers a document-level click handler; with the "
        "backdrop gone this would close the panel on any click on the page"
    )


def test_escape_only_closes_the_chat_from_inside_it():
    """Non-modal means the page keeps focus and keeps working. A global Escape
    handler would steal the key from whatever the user is actually in -- the
    SQL editor, a filter, the drill drawer."""
    js = (TEMPLATES / "js" / "_reporting_ai_js.html").read_text(encoding="utf-8")
    assert "panel.contains(document.activeElement)" in js, (
        "Escape closes the chat regardless of where focus is; it should only "
        "do so when focus is inside the panel"
    )


def test_chat_panel_body_stays_selectable():
    """The panel header is a drag handle, so it sets user-select: none -- a
    text selection started on the handle would fight the drag. That must stay
    scoped to the header: the thread below it holds the assistant's answers and
    generated SQL, which are there to be copied."""
    text = (CSS / "reporting.css").read_text(encoding="utf-8")

    head = _rule_body(text, ".reporting-chat-head")
    assert _declaration(head, "user-select") == "none", (
        ".reporting-chat-head lost user-select: none; dragging it will select "
        "the title text instead of moving the panel"
    )

    panel = _rule_body(text, ".reporting-chat-panel")
    assert _declaration(panel, "user-select") is None, (
        ".reporting-chat-panel sets user-select on the whole panel, which "
        "makes the assistant's answers and generated SQL impossible to select "
        "or copy. Keep it on .reporting-chat-head only."
    )


def test_chat_panel_is_reachable_after_a_drag():
    """Dragging writes inline left/top and clears right/bottom. The panel is
    clamped to the viewport in JS; the CSS must not also pin it with a
    !important offset, or the clamp silently does nothing."""
    panel = _rule_body((CSS / "reporting.css").read_text(encoding="utf-8"), ".reporting-chat-panel")
    for prop in ("right", "bottom", "left", "top"):
        value = _declaration(panel, prop)
        if value is not None:
            assert "!important" not in value, (
                f".reporting-chat-panel pins {prop} with !important; the drag "
                f"handler's inline offsets cannot override it"
            )


# --------------------------------------------------------------------------
# Theme pre-paint
# --------------------------------------------------------------------------


def test_prepaint_does_not_inline_a_body_background():
    """The pre-paint script paints <html> inline because nothing has told the
    browser what "dark" means yet. <body> is different: _header.css already
    carries `body` and `html.dark body` background rules, and an inline style
    on body outranks both *permanently* -- the runtime dark-mode toggle flips
    html.dark, the stylesheet updates, and the stale inline colour wins anyway.

    Anything the pre-paint needs to say about body belongs in a class or a
    custom property the stylesheet reads, never element.style."""
    text = (TEMPLATES / "_theme_prepaint.html").read_text(encoding="utf-8")
    assert not re.search(r"document\.body\.style\.backgroundColor\s*=", text), (
        "the pre-paint script assigns document.body.style.backgroundColor. "
        "Inline styles beat html.dark body in _header.css, so the dark-mode "
        "toggle leaves body stuck on the boot-time colour."
    )


def test_prepaint_still_paints_the_root_element():
    """The counterpart guard: dropping the <html> inline paint brings the
    original flash-of-white back on any page whose stylesheet lands late."""
    text = (TEMPLATES / "_theme_prepaint.html").read_text(encoding="utf-8")
    assert re.search(r"\bd\.style\.backgroundColor\s*=", text), (
        "the pre-paint script no longer paints documentElement; pages will "
        "flash the UA-default white before the stylesheet applies"
    )


def test_series_tokens_exist_in_both_themes():
    """A categorical chart palette must be defined independently of the accent
    (which the user can switch to any of seven hues) and must have dark twins."""
    css = (CSS / "nexora-ui.css").read_text(encoding="utf-8")
    # Split on the dark ROOT block, not the bare string: "html.dark" also
    # appears in the file's table-of-contents comment on line 11 and in the
    # per-accent html.dark[data-accent="..."] blocks far below.
    light, dark = css.split("\nhtml.dark {", 1)
    for i in range(1, 6):
        assert f"--nx-series-{i}:" in light, f"--nx-series-{i} missing from the light palette"
        assert f"--nx-series-{i}:" in dark, f"--nx-series-{i} missing from the dark palette"


def test_slim_control_height_token_exists():
    css = (CSS / "nexora-ui.css").read_text(encoding="utf-8")
    assert "--ctl-h:" in css
