"""E2E counterparts to tests/unit/test_ui_chrome_regressions.py.

The unit file pins the CSS and markup; this one proves the properties survive
a real cascade and a real layout -- geometry that overlaps, a rail that covers
the page, a panel that will not move. Every one of these covers a bug that
looked fine in the markup and only showed up on screen.

admin@test.local has the workitems + reporting perms these pages need.
"""

import pytest
from playwright.sync_api import expect


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_load_state("domcontentloaded")


def _box(page, selector):
    """Bounding box of the first match, as a dict. Fails loudly if the element
    is not laid out (Playwright returns None for display:none)."""
    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"{selector} has no layout box"
    return box


# --------------------------------------------------------------------------
# Workitems search field
# --------------------------------------------------------------------------


@pytest.mark.flaky_e2e
def test_search_placeholder_starts_clear_of_the_magnifier(nexora_server, page):
    """The reported symptom: the glyph and the placeholder painted on top of
    each other. Assert the geometry directly -- where the input's text box
    begins vs. where the icon ends."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator('[data-testid="workitems-search"]')).to_be_visible()

    icon = _box(page, ".nx-wi-search i")
    field = _box(page, '[data-testid="workitems-search"]')
    text_starts_at = field["x"] + page.eval_on_selector(
        '[data-testid="workitems-search"]',
        "el => parseFloat(getComputedStyle(el).paddingLeft)",
    )

    icon_ends_at = icon["x"] + icon["width"]
    assert text_starts_at >= icon_ends_at, (
        f"the search text begins at x={text_starts_at:.1f} but the magnifier "
        f"runs to x={icon_ends_at:.1f} -- they overlap by "
        f"{icon_ends_at - text_starts_at:.1f}px"
    )


@pytest.mark.flaky_e2e
def test_clicking_the_magnifier_focuses_the_search_field(nexora_server, page):
    """pointer-events-none, proven by behaviour rather than by class name."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    expect(page.locator('[data-testid="workitems-search"]')).to_be_visible()

    icon = _box(page, ".nx-wi-search i")
    page.mouse.click(icon["x"] + icon["width"] / 2, icon["y"] + icon["height"] / 2)

    focused = page.evaluate("document.activeElement && document.activeElement.id")
    assert focused == "searchInput", (
        f"clicking the magnifier focused {focused!r}, not the search input -- "
        f"the icon is swallowing the click"
    )


# --------------------------------------------------------------------------
# Process scope picker (issue #206)
# --------------------------------------------------------------------------


@pytest.mark.flaky_e2e
def test_scope_checkboxes_render_as_visible_boxes(nexora_server, page):
    """They collapsed to a few pixels and read as bullet dots."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-process-filter-btn"]')
    expect(page.locator('[data-testid="workitems-process-filter-menu"]')).to_be_visible()

    box = _box(page, ".nx-scope-menu .nx-scope-row input")
    assert box["width"] >= 14 and box["height"] >= 14, (
        f"scope checkbox renders {box['width']:.1f}x{box['height']:.1f}px -- "
        f"too small to read as a checkbox (issue #206)"
    )


@pytest.mark.flaky_e2e
def test_scope_checked_and_unchecked_look_different(nexora_server, page):
    """The actual complaint: "i cant see what i have selected". A checked box
    is filled with the accent colour, an unchecked one with the card surface --
    if those two ever resolve to the same paint the control is useless."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.click('[data-testid="workitems-process-filter-btn"]')
    expect(page.locator('[data-testid="workitems-process-filter-menu"]')).to_be_visible()

    rows = page.locator(".nx-scope-menu .nx-scope-proc input")
    if rows.count() == 0:
        pytest.skip("no processes configured in this environment")

    first = rows.first
    styles = (
        "el => { const s = getComputedStyle(el); return [s.backgroundColor, s.backgroundImage]; }"
    )

    first.uncheck()
    off_bg, off_img = page.evaluate(styles, first.element_handle())
    first.check()
    on_bg, on_img = page.evaluate(styles, first.element_handle())

    assert (on_bg, on_img) != (off_bg, off_img), (
        f"checked and unchecked paint identically ({on_bg}, {on_img}); " f"selection is invisible"
    )
    assert on_img != "none", (
        "the checked box has no checkmark image; appearance:none checkboxes "
        "rely on background-image for the tick"
    )


# --------------------------------------------------------------------------
# Sidebar rail
# --------------------------------------------------------------------------


@pytest.mark.flaky_e2e
def test_hovering_the_unpinned_sidebar_does_not_cover_the_page(nexora_server, page):
    """Unpinned, hovering expands the rail 64px -> 220px. It used to paint
    straight over the page because only the pinned state reserved room."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    # Make sure we are testing the unpinned case.
    page.evaluate("document.documentElement.classList.remove('sidebar-pinned')")
    page.evaluate("document.getElementById('nexora-sidebar').classList.remove('pinned')")

    page.hover("#nexora-sidebar")
    page.wait_for_timeout(450)  # the width + padding transitions are ~300ms

    sidebar = _box(page, "#nexora-sidebar")
    main = _box(page, "main")

    sidebar_right = sidebar["x"] + sidebar["width"]
    assert main["x"] >= sidebar_right, (
        f"the expanded sidebar reaches x={sidebar_right:.1f} but main content "
        f"starts at x={main['x']:.1f} -- the rail is covering "
        f"{sidebar_right - main['x']:.1f}px of the page"
    )


@pytest.mark.flaky_e2e
def test_collapsed_sidebar_leaves_the_page_where_it_was(nexora_server, page):
    """Counterpart guard: reserving room on hover must not strand a gutter
    once the pointer leaves."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.evaluate("document.documentElement.classList.remove('sidebar-pinned')")
    page.evaluate("document.getElementById('nexora-sidebar').classList.remove('pinned')")

    # body animates its padding on load; sample the resting value only once
    # that transition has settled, or we compare against a mid-flight number.
    page.wait_for_timeout(450)
    resting = page.evaluate("getComputedStyle(document.body).paddingLeft")
    page.hover("#nexora-sidebar")
    page.wait_for_timeout(450)
    page.mouse.move(page.viewport_size["width"] / 2, page.viewport_size["height"] / 2)
    page.wait_for_timeout(450)

    assert (
        page.evaluate("getComputedStyle(document.body).paddingLeft") == resting
    ), "body kept the expanded padding after the pointer left the sidebar"


# --------------------------------------------------------------------------
# Reporting chat panel (issue #205)
# --------------------------------------------------------------------------


def _open_chat(page, base):
    page.goto(f"{base}/reporting?tab=advanced")
    page.get_by_test_id("reporting-chat-toggle").click()
    expect(page.get_by_test_id("reporting-chat-panel")).to_be_visible()


@pytest.mark.flaky_e2e
def test_chat_panel_can_be_dragged_by_its_header(nexora_server, page):
    _login(page, nexora_server)
    _open_chat(page, nexora_server)

    before = _box(page, '[data-testid="reporting-chat-panel"]')
    head = _box(page, ".reporting-chat-head")

    page.mouse.move(head["x"] + head["width"] / 2, head["y"] + head["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        head["x"] + head["width"] / 2 - 180, head["y"] + head["height"] / 2 - 120, steps=10
    )
    page.mouse.up()

    after = _box(page, '[data-testid="reporting-chat-panel"]')
    assert (round(after["x"]), round(after["y"])) != (
        round(before["x"]),
        round(before["y"]),
    ), "the chat panel did not move when its header was dragged"


@pytest.mark.flaky_e2e
def test_dragged_chat_panel_stays_inside_the_viewport(nexora_server, page):
    """The drag handler clamps to the viewport; a panel dragged off-screen
    could not be dragged back."""
    _login(page, nexora_server)
    _open_chat(page, nexora_server)

    head = _box(page, ".reporting-chat-head")
    page.mouse.move(head["x"] + head["width"] / 2, head["y"] + head["height"] / 2)
    page.mouse.down()
    page.mouse.move(-900, -900, steps=10)  # yank hard past the top-left corner
    page.mouse.up()

    panel = _box(page, '[data-testid="reporting-chat-panel"]')
    view = page.viewport_size
    assert (
        panel["x"] >= -1 and panel["y"] >= -1
    ), f"panel escaped to ({panel['x']:.1f}, {panel['y']:.1f})"
    assert panel["x"] + panel["width"] <= view["width"] + 1
    assert panel["y"] + panel["height"] <= view["height"] + 1


@pytest.mark.flaky_e2e
def test_page_stays_usable_while_the_chat_is_open(nexora_server, page):
    """The whole point of non-modal (issue #205): no backdrop intercepting
    clicks, so the report underneath is still operable. Proven by hit-testing
    -- ask the browser what element is actually at a point over the page and
    check it is not some overlay."""
    _login(page, nexora_server)
    _open_chat(page, nexora_server)

    # A point on the page, deliberately away from the bottom-right panel.
    at_point = page.evaluate(
        "() => { const el = document.elementFromPoint(window.innerWidth * 0.3,"
        " window.innerHeight * 0.35); return el ? el.className.toString() : null; }"
    )
    assert at_point is not None
    assert "backdrop" not in at_point, (
        f"a backdrop is covering the page at 30%/35% (hit {at_point!r}); the "
        f"report is not clickable while the chat is open"
    )


@pytest.mark.flaky_e2e
def test_clicking_the_page_leaves_the_chat_open(nexora_server, page):
    """Modal drawers close on outside-click. A non-modal tool window must not
    -- otherwise working on the report you moved it away from dismisses it."""
    _login(page, nexora_server)
    _open_chat(page, nexora_server)

    page.mouse.click(page.viewport_size["width"] * 0.3, page.viewport_size["height"] * 0.35)
    page.wait_for_timeout(200)

    expect(page.get_by_test_id("reporting-chat-panel")).to_be_visible()


@pytest.mark.flaky_e2e
def test_escape_inside_the_chat_closes_it(nexora_server, page):
    _login(page, nexora_server)
    _open_chat(page, nexora_server)

    page.get_by_test_id("reporting-chat-input").focus()
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    expect(page.get_by_test_id("reporting-chat-panel")).to_be_hidden()


@pytest.mark.flaky_e2e
def test_escape_outside_the_chat_leaves_it_open(nexora_server, page):
    """Escape belongs to whatever the user is focused in. The chat must not
    swallow it globally just because it happens to be open."""
    _login(page, nexora_server)
    _open_chat(page, nexora_server)

    # Focus a real control on the page. `document.body.focus()` will not do:
    # body is not focusable without a tabindex, so it silently leaves focus in
    # the chat input and the test passes for the wrong reason.
    outside = page.locator("#rpSource")
    if outside.count() == 0:
        pytest.skip("no focusable source control on this build of the page")
    outside.focus()

    moved = page.evaluate(
        "() => { const p = document.getElementById('rpChatPanel');"
        " return !p.contains(document.activeElement); }"
    )
    assert moved, "focus never left the chat panel; the test would prove nothing"

    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    expect(page.get_by_test_id("reporting-chat-panel")).to_be_visible()


@pytest.mark.flaky_e2e
def test_chat_answers_can_be_selected(nexora_server, page):
    """The header is a drag handle (user-select: none). That must not leak to
    the thread -- the answers and generated SQL exist to be copied."""
    _login(page, nexora_server)
    _open_chat(page, nexora_server)

    for selector, expected in (
        (".reporting-chat-head", "none"),
        (".reporting-chat-thread", None),
    ):
        value = page.eval_on_selector(selector, "el => getComputedStyle(el).userSelect")
        if expected == "none":
            assert value == "none", f"{selector} should be undraggable text, got {value!r}"
        else:
            assert value != "none", (
                f"{selector} has user-select: none -- the assistant's answers "
                f"cannot be selected or copied"
            )


# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------


@pytest.mark.flaky_e2e
def test_dark_mode_toggle_repaints_the_body(nexora_server, page):
    """Regression guard for the pre-paint script: anything that writes an
    inline background onto <body> outranks `html.dark body` forever, and the
    toggle stops working even though the class flips."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")

    before = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.click('[data-testid="header-dark-mode-toggle"]')
    page.wait_for_timeout(250)
    after = page.evaluate("getComputedStyle(document.body).backgroundColor")

    assert before != after, (
        f"body stayed {before} across a dark-mode toggle -- an inline style is "
        f"beating the stylesheet"
    )
    assert page.evaluate("document.body.style.backgroundColor") == "", (
        "something wrote an inline background onto <body>; it will pin the "
        "page to its boot-time theme"
    )


@pytest.mark.flaky_e2e
def test_api_docs_paints_dark_before_the_stylesheets_land(nexora_server, page):
    """The reported symptom: /api-docs flashed white on load in dark mode.
    The root element is painted inline by the pre-paint script, so it is dark
    from the very first frame regardless of stylesheet timing.

    Dark is set through the real toggle rather than a localStorage poke, so the
    preference lands wherever the app actually keeps it and the pre-paint reads
    it back the same way a returning user would."""
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    if not page.evaluate("document.documentElement.classList.contains('dark')"):
        page.click('[data-testid="header-dark-mode-toggle"]')
        page.wait_for_timeout(300)

    page.goto(f"{nexora_server}/api-docs")
    root_inline = page.evaluate("document.documentElement.style.backgroundColor")
    assert root_inline in ("rgb(15, 23, 42)", "#0f172a"), (
        f"documentElement was not pre-painted dark (got {root_inline!r}); "
        f"the page will flash white before the stylesheet applies"
    )
    assert page.evaluate("document.documentElement.classList.contains('dark')")
