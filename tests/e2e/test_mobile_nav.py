"""E2E tests for the phone tab bar and bottom sheet (#354).

The point of these tests is the *gate*, not just the bar. The phone layout is
behind `(max-width: 768px) and (pointer: coarse)`, so both directions are
pinned here:

  - a touch phone at 390px gets the tab bar and loses the hamburger;
  - a 390px window with a MOUSE keeps the hamburger and never sees the bar.

That second one is the requirement: nexora must never show the phone layout on
a computer, including a half-screen window or a display at 200% browser zoom,
both of which put a desktop under 768 CSS px.

`page.set_viewport_size()` alone is NOT enough to exercise this -- it resizes
the viewport but the browser still reports `pointer: fine`, so a width-only
test would pass while testing nothing. The touch tests below use a
real mobile context (`has_touch` + `is_mobile`).
"""

import re

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from tests.e2e.test_reporting_simple import _stub_catalogs

PHONE = {"width": 390, "height": 844}


def _tune(page):
    """Same page tuning the autouse `_e2e_page_setup` fixture applies to the
    stock `page` fixture -- short timeouts, and don't wait on CDN assets."""
    page.set_default_timeout(8000)
    page.set_default_navigation_timeout(15000)
    _orig_goto = page.goto

    def _goto(url, **kwargs):
        kwargs.setdefault("wait_until", "domcontentloaded")
        return _orig_goto(url, **kwargs)

    page.goto = _goto
    return page


@pytest.fixture()
def phone_page(browser):
    """A real touch phone: 390x844, `pointer: coarse`, `hover: none`.

    Firefox does not implement `is_mobile`, so these tests are chromium/webkit
    only -- the gate is a CSS media query, and the suite already runs the
    cross-browser checks it needs in test_cross_browser.py.
    """
    if browser.browser_type.name == "firefox":
        pytest.skip("is_mobile is unsupported on Firefox")
    context = browser.new_context(viewport=PHONE, has_touch=True, is_mobile=True)
    page = _tune(context.new_page())
    yield page
    context.close()


@pytest.fixture()
def narrow_desktop_page(browser):
    """A 390px-wide window on a normal mouse machine.

    Stands in for the two cases that trip a width-only media query: a window
    snapped to half a wide monitor, and a big display at 200% browser zoom.
    No `has_touch`, no `is_mobile` -- so `pointer: fine` and `hover: hover`.
    """
    context = browser.new_context(viewport=PHONE)
    page = _tune(context.new_page())
    yield page
    context.close()


def _login(page, base, who="admin@test.local"):
    page.goto(f"{base}/dev/login/{who}")
    page.wait_for_url("**/dashboard")


def _assert_sheet_is_on_screen(page):
    """The sheet is really raised, not just carrying the `.open` class.

    Worth the extra check: the class is set by JS, but whether the panel
    actually moves is decided by CSS specificity, and those can disagree
    silently -- see test_sheet_opens_for_a_user_who_pinned_the_sidebar.
    """
    # The sheet slides up over 0.28s, so poll rather than measure the instant
    # the class lands -- otherwise this catches it mid-animation near the
    # bottom and fails for a reason that has nothing to do with the layout.
    try:
        page.wait_for_function(
            "() => { const r = document.getElementById('nexora-sidebar')"
            ".getBoundingClientRect();"
            " return r.height > 200 && r.top < window.innerHeight - 200; }",
            timeout=5000,
        )
    except PlaywrightTimeoutError:
        box = page.evaluate(
            "() => { const r = document.getElementById('nexora-sidebar')"
            ".getBoundingClientRect();"
            " return {top: Math.round(r.top), height: Math.round(r.height),"
            " vh: window.innerHeight,"
            " transform: getComputedStyle(document.getElementById('nexora-sidebar')).transform,"
            " cls: document.getElementById('nexora-sidebar').className}; }"
        )
        raise AssertionError(f"the sheet never came up on screen: {box}") from None


# --------------------------------------------------------------- the gate --


@pytest.mark.flaky_e2e
def test_tabbar_shows_on_a_touch_phone(nexora_server, phone_page):
    _login(phone_page, nexora_server)
    expect(phone_page.locator('[data-testid="mobilenav-bar"]')).to_be_visible()
    # The floating hamburger is the drawer's control and has no place here.
    expect(phone_page.locator('[data-testid="header-burger"]')).to_be_hidden()


@pytest.mark.flaky_e2e
def test_tabbar_never_shows_on_a_narrow_desktop_window(nexora_server, narrow_desktop_page):
    """The regression test for "never the phone version on a computer".

    Identical viewport to the phone test above -- only the pointer differs.
    """
    page = narrow_desktop_page
    _login(page, nexora_server)

    # Sanity-check the premise: this context really does report a fine pointer.
    assert page.evaluate(
        "() => matchMedia('(pointer: fine)').matches"
    ), "test setup is wrong -- this context should behave like a mouse machine"

    expect(page.locator('[data-testid="mobilenav-bar"]')).to_be_hidden()
    # ...and the existing drawer still works at this width.
    expect(page.locator('[data-testid="header-burger"]')).to_be_visible()
    page.click('[data-testid="header-burger"]')
    expect(page.locator("#nexora-sidebar")).to_have_class(re.compile(r"\bopen\b"))


# ------------------------------------------------------------------- bar --


@pytest.mark.flaky_e2e
def test_more_slot_opens_the_sheet(nexora_server, phone_page):
    page = phone_page
    _login(page, nexora_server)
    more = page.locator('[data-testid="mobilenav-more"]')
    expect(more).to_have_attribute("aria-expanded", "false")
    more.click()
    expect(page.locator("#nexora-sidebar")).to_have_class(re.compile(r"\bopen\b"))
    expect(more).to_have_attribute("aria-expanded", "true")
    _assert_sheet_is_on_screen(page)
    # Everything the drawer holds is reachable from the sheet.
    expect(page.locator('[data-testid="header-nav-admin-toggle"]')).to_be_visible()


@pytest.mark.flaky_e2e
def test_sheet_opens_for_a_user_who_pinned_the_sidebar(nexora_server, phone_page):
    """A pinned sidebar must not keep the sheet parked off-screen.

    `html.sidebar-pinned` is set pre-paint from a saved UI pref, and as a
    descendant selector it outranks `#nexora-sidebar.open`. The first cut of
    this feature carried the closed transform on that higher-specificity rule,
    so for anyone who had ever pinned the sidebar on a desktop -- which is to
    say the heaviest users -- tapping More dimmed the page and raised nothing.
    The `.open` class was still set, so a class-only assertion passed happily.
    """
    page = phone_page
    _login(page, nexora_server)
    page.evaluate("() => document.documentElement.classList.add('sidebar-pinned')")
    more = page.locator('[data-testid="mobilenav-more"]')
    # aria-expanded flips in the same handler that sets `.open`, so waiting on
    # it proves header.js was bound and the tap actually registered -- a click
    # that lands before DOMContentLoaded would otherwise leave the sheet shut
    # and fail this test for the wrong reason.
    more.click()
    expect(more).to_have_attribute("aria-expanded", "true")
    _assert_sheet_is_on_screen(page)


@pytest.mark.flaky_e2e
def test_sheet_closes_on_backdrop_tap(nexora_server, phone_page):
    page = phone_page
    _login(page, nexora_server)
    page.click('[data-testid="mobilenav-more"]')
    page.click("#sidebar-backdrop")
    expect(page.locator("#nexora-sidebar")).not_to_have_class(re.compile(r"\bopen\b"))


@pytest.mark.flaky_e2e
def test_every_slot_leads_somewhere_real(nexora_server, phone_page):
    """No dead tabs: each rendered slot is a link the user may actually open.

    Run as a plain user, who holds fewer permissions than admin -- a slot that
    leaked past its permission gate would 403 here.
    """
    page = phone_page
    _login(page, nexora_server, who="user@test.local")

    hrefs = page.eval_on_selector_all(
        ".nx-tabbar a.nx-tabbar-item", "els => els.map(e => e.getAttribute('href'))"
    )
    assert hrefs, "the tab bar rendered no navigation slots at all"
    for href in hrefs:
        assert href, "a slot rendered without an href"
        resp = page.goto(f"{nexora_server}{href}")
        assert resp.status < 400, f"slot {href} answered {resp.status}"


@pytest.mark.flaky_e2e
def test_dashboard_does_not_scroll_sideways_on_a_phone(nexora_server, phone_page):
    """The guard #136 and #143 (both 375px overflow bugs) did not have."""
    page = phone_page
    _login(page, nexora_server)
    # Measure a settled page, not a loading one. Two waits, both needed:
    #   - the tab bar turns visible only once _header.css has applied, so it is
    #     the signal that the phone layout is actually in place;
    #   - then the measurement itself has to settle. Every `<i class="fas">`
    #     renders as fallback text until the Font Awesome webfont applies, and
    #     is far wider than the glyph it becomes -- which transiently pushes
    #     the page ~24px past the viewport during load. Neither the `load`
    #     event nor `document.fonts.status` is a reliable "done" signal here
    #     (webfonts do not block `load`, and the status flips back to
    #     "loading" as each later face starts), so wait on the condition under
    #     test and only fail if it never becomes true.
    expect(page.locator('[data-testid="mobilenav-bar"]')).to_be_visible()
    try:
        page.wait_for_function(
            "() => document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth <= 1",
            timeout=8000,
        )
        return
    except PlaywrightTimeoutError:
        pass

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    # Name the offenders -- "it overflows by 40px" alone sends the next person
    # hunting through the whole page.
    culprits = page.evaluate(
        "() => [...document.querySelectorAll('*')]"
        ".filter(e => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1)"
        ".slice(0, 5)"
        ".map(e => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string'"
        " ? '.' + e.className.trim().split(/\\s+/).join('.') : '')"
        " + ' -> ' + Math.round(e.getBoundingClientRect().right) + 'px')"
    )
    assert (
        overflow <= 1
    ), f"the dashboard scrolls sideways by {overflow}px at 390px; widest: {culprits}"


# --------------------------------------------- signed-out pages on a phone --


@pytest.mark.flaky_e2e
@pytest.mark.parametrize("path", ["/", "/login"])
def test_signed_out_pages_have_thumb_sized_controls(nexora_server, phone_page, path):
    """The landing and login pages are what everyone meets before signing in,
    and both had controls around half the size a thumb needs.

    44px is the floor Apple and Google both publish. The footer links measured
    20px tall, the show-password eye 30px wide -- the control most likely to be
    tapped on a phone, where typing a password blind is hardest.

    The rules behind this are keyed on `pointer: coarse` rather than a width,
    because how big a control must be follows the finger, not the screen.
    """
    page = phone_page
    page.goto(f"{nexora_server}{path}")
    page.wait_for_load_state("load")

    too_small = page.evaluate(
        "() => [...document.querySelectorAll('a, button')]"
        ".map(e => ({ r: e.getBoundingClientRect(),"
        "            id: e.getAttribute('data-testid') || e.innerText.trim().slice(0, 20) }))"
        ".filter(x => x.r.height > 0 && x.r.width > 0"
        "          && (x.r.height < 44 || x.r.width < 44))"
        ".map(x => x.id + ' ' + Math.round(x.r.width) + 'x' + Math.round(x.r.height))"
    )
    assert too_small == [], f"controls too small to tap on {path}: {too_small}"


@pytest.mark.flaky_e2e
@pytest.mark.parametrize("path", ["/", "/login"])
def test_signed_out_pages_do_not_scroll_sideways(nexora_server, phone_page, path):
    page = phone_page
    page.goto(f"{nexora_server}{path}")
    page.wait_for_load_state("load")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"{path} scrolls sideways by {overflow}px at 390px"


@pytest.mark.flaky_e2e
def test_workitems_overview_fits_a_phone(nexora_server, phone_page):
    """The busiest page in the app, and the one most likely to regress.

    Three separate rows -- the export/import cluster, the list header and the
    status tab strip -- were flex rows sized for a desktop that could neither
    shrink nor wrap, and together they pushed the page 27px sideways.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.wait_for_load_state("load")
    page.wait_for_timeout(600)  # the list renders from JS

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"the workitems list scrolls sideways by {overflow}px"

    # This page is also the guard for the shared touch-sizing rules in
    # nexora-ui.css (.nx-btn / .nx-btn--sm / .nx-tab / .nx-segmented__btn /
    # .pagination-link). It uses all five, and those rules are what fixed the
    # thirteen Generali pages -- which cannot be exercised here, because the
    # TEST environment has no Generali database (sql/test/seed.sql seeds the
    # permission codes but no live Generali/Octopus connection).
    #
    # Rows are excluded on purpose: the per-row checkbox and details chevron
    # are deliberately left under 44px so the list still fits a useful number
    # of rows on screen. See the CSS comment in workitems_overview.css.
    too_small = page.evaluate(
        "() => [...document.querySelectorAll("
        "  '.nx-btn, .nx-tab, .nx-segmented__btn, .pagination-link')]"
        ".filter(e => !e.closest('tbody') && !e.closest('#nexora-sidebar')"
        "          && !e.closest('.nx-tabbar'))"
        ".map(e => ({ r: e.getBoundingClientRect(),"
        "             id: e.getAttribute('data-testid')"
        "                 || e.innerText.trim().slice(0, 14) }))"
        ".filter(x => x.r.width > 0 && x.r.height > 0"
        "          && (x.r.height < 43.5 || x.r.width < 43.5))"
        ".map(x => x.id + ' ' + Math.round(x.r.width) + 'x' + Math.round(x.r.height))"
    )
    assert too_small == [], f"shared controls too small to tap: {too_small}"


@pytest.mark.flaky_e2e
def test_bulk_action_bar_clears_the_tab_bar(nexora_server, phone_page):
    """The floating bulk bar sat at bottom: 12px -- underneath the phone tab
    bar, so selecting rows hid the actions behind the navigation."""
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.wait_for_load_state("load")
    page.wait_for_timeout(600)

    gap = page.evaluate(
        "() => { const b = document.getElementById('bulk-action-bar');"
        " const t = document.querySelector('.nx-tabbar');"
        " if (!b || !t) return null;"
        " return Math.round(t.getBoundingClientRect().top"
        "                   - b.getBoundingClientRect().bottom); }"
    )
    assert gap is not None, "bulk action bar or tab bar missing from the page"
    assert gap >= 0, f"the bulk action bar overlaps the tab bar by {-gap}px"


@pytest.mark.flaky_e2e
@pytest.mark.parametrize("path", ["/admin", "/admin/logs", "/admin/access_control"])
def test_admin_pages_fit_a_phone(nexora_server, phone_page, path):
    """Admin pages, unlike the Generali ones, do render in the TEST database,
    so they can carry the guard for the shared form-control sizing.

    None of the admin pages overflowed -- their wide tables already scroll
    inside their own containers -- so target size was the whole problem:
    `.nx-input` rendered 41px and `.nx-select` 39px, which is what every
    admin search and filter row is built from, and admin-logs' own time-range
    presets were 31-33px.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}{path}")
    page.wait_for_load_state("load")
    page.wait_for_timeout(600)

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"{path} scrolls sideways by {overflow}px"

    too_small = page.evaluate(
        "() => [...document.querySelectorAll("
        "  'button, .nx-btn, .nx-input, .nx-select, .nx-tab, .pagination-link')]"
        ".filter(e => !e.closest('tbody') && !e.closest('#nexora-sidebar')"
        "          && !e.closest('.nx-tabbar'))"
        ".map(e => ({ r: e.getBoundingClientRect(),"
        "             id: e.getAttribute('data-testid')"
        "                 || e.innerText.trim().slice(0, 14) }))"
        ".filter(x => x.r.width > 0 && x.r.height > 0"
        "          && (x.r.height < 43.5 || x.r.width < 43.5))"
        ".map(x => x.id + ' ' + Math.round(x.r.width) + 'x' + Math.round(x.r.height))"
    )
    assert too_small == [], f"controls too small to tap on {path}: {too_small}"


@pytest.mark.flaky_e2e
def test_installed_app_has_its_own_reload(nexora_server, phone_page):
    """An installed home-screen app runs with no browser chrome -- no address
    bar, no reload button. Android keeps pull-to-refresh there; iOS does not,
    and iOS does not support `minimal-ui` either, so without this an installed
    nexora on an iPhone cannot reload a page at all.

    Two halves, tested separately because the `display-mode: standalone` gate
    cannot be emulated from here -- neither CDP's Emulation.setEmulatedMedia
    nor a --app= launch makes Chromium report it:

      1. the control is hidden in a normal browser tab, where the browser's
         own reload button makes it redundant, and the gate rule exists;
      2. the click really reloads.
    """
    page = phone_page
    _login(page, nexora_server)

    btn = page.locator("#nx-reload")
    assert btn.count() == 1, "the reload control is not in the page at all"
    assert (
        btn.evaluate("e => getComputedStyle(e).display") == "none"
    ), "the reload control should be hidden in a browser tab"

    gate = page.evaluate(
        "() => { for (const sh of document.styleSheets) {"
        "   let rs; try { rs = sh.cssRules; } catch (e) { continue; }"
        "   for (const r of rs) {"
        "     if (!r.conditionText || !r.conditionText.includes('display-mode')) continue;"
        "     for (const inner of r.cssRules || [])"
        "       if (inner.selectorText && inner.selectorText.includes('sidebar-reload'))"
        "         return r.conditionText;"
        "   } } return null; }"
    )
    assert (
        gate == "(display-mode: standalone)"
    ), f"the standalone gate for the reload control is missing or changed: {gate}"

    # ...and it works when shown. Forced visible because the gate cannot be
    # emulated; this exercises the handler, not the media query.
    page.click('[data-testid="mobilenav-more"]')
    page.wait_for_timeout(500)
    page.evaluate(
        "() => { window.__beforeReload = true;"
        " document.getElementById('nx-reload').style.display = 'flex'; }"
    )
    page.locator("#nx-reload").scroll_into_view_if_needed()
    page.click("#nx-reload")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(800)
    assert page.evaluate(
        "() => window.__beforeReload === undefined"
    ), "clicking reload did not reload the page"


@pytest.mark.flaky_e2e
@pytest.mark.parametrize(
    ("path", "expected"),
    [("/dashboard", "Dashboard"), ("/workitems", "Workitems"), ("/reporting", "Reporting")],
)
def test_the_bar_marks_the_page_you_are_on(nexora_server, phone_page, path, expected):
    """Exactly one slot is marked, and it is the right one.

    This was broken for the two pages people open most. The bar first reused
    the sidebar's `active` flag, which asks "is the sidebar's *Global* entry
    the current page" -- and for anyone scoped to a tenant the answer is
    always no: a tenant-mounted Dashboard sets active_page to
    `tenant_<code>_dashboard` (0097) and Workitems to `tenant_<code>_workitems`
    (0098). In the sidebar that is correct, because the tenant's own group
    lights instead; the bar has no tenant group, so nothing lit at all and
    only /reporting ever looked right.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}{path}")
    page.wait_for_load_state("load")
    page.wait_for_timeout(400)

    marked = page.eval_on_selector_all(
        ".nx-tabbar-item--active .nx-tabbar-label", "els => els.map(e => e.textContent.trim())"
    )
    assert marked == [expected], f"{path} should mark exactly {expected!r}, marked {marked}"

    # Colour alone is not enough of a signal, so the label also carries weight.
    weight = page.evaluate(
        "() => getComputedStyle(document.querySelector("
        "  '.nx-tabbar-item--active .nx-tabbar-label')).fontWeight"
    )
    assert int(weight) >= 600, f"the active label should be bolder, got {weight}"

    # ...and the icon is still drawn. Font Awesome renders its glyph in
    # `.fas::before` via `content`, so any rule that also targets that
    # pseudo-element REPLACES the icon rather than decorating it. The first
    # attempt at the active pill did exactly that: `content: ""`, and the
    # active tab's icon vanished, measuring 0x0. Nothing else in this file
    # would have caught it -- the class was set, the colour was right, the
    # label was bold, and the icon was simply gone.
    icon = page.evaluate(
        "() => { const i = document.querySelector("
        "          '.nx-tabbar-item--active .nx-tabbar-icon');"
        "        if (!i) return null;"
        "        const r = i.getBoundingClientRect();"
        "        return {content: getComputedStyle(i, '::before').content,"
        "                w: Math.round(r.width), h: Math.round(r.height)}; }"
    )
    assert icon, "the active slot has no icon element"
    assert icon["content"] not in (
        '""',
        "none",
        "",
    ), f"the active tab's icon glyph was overwritten: content={icon['content']!r}"
    assert icon["w"] > 0 and icon["h"] > 0, f"the active tab's icon collapsed: {icon}"


@pytest.mark.flaky_e2e
def test_eddard_chat_panel_fits_a_phone(nexora_server, phone_page):
    """The reporting assistant's panel must stay between the status bar and
    the tab bar.

    It was anchored `bottom: 20px` with `height: calc(100dvh - 40px)`. `dvh`
    counts the whole screen including the status bar and home indicator, so
    once the pages opted into `viewport-fit=cover` the panel grew taller than
    the usable area and its top slid off-screen -- taking the header and its
    close button with it, leaving no way to dismiss Eddard on a phone.

    Comparisons here are rect-against-rect on purpose. getBoundingClientRect
    reports scaled pixels under mobile emulation while getComputedStyle
    reports CSS pixels; mixing the two invents discrepancies that are not
    there.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1200)

    page.click('[data-testid="reporting-chat-toggle"]')
    page.wait_for_timeout(800)

    box = page.evaluate(
        "() => { const p = document.querySelector('.reporting-chat-panel');"
        "        const t = document.querySelector('.nx-tabbar');"
        "        const h = p.querySelector('.reporting-chat-head');"
        "        if (!p || !t || !h) return null;"
        "        const pr = p.getBoundingClientRect(), tr = t.getBoundingClientRect(),"
        "              hr = h.getBoundingClientRect();"
        "        return {panelTop: pr.top, panelBottom: pr.bottom,"
        "                headTop: hr.top, headBottom: hr.bottom, barTop: tr.top,"
        "                barShown: getComputedStyle(t).display !== 'none'}; }"
    )
    assert box, "chat panel, its header, or the tab bar is missing"
    assert box["headTop"] >= 0, (
        f"the chat header is off the top of the screen ({box['headTop']}px) -- "
        "its close button is unreachable"
    )
    # Only meaningful while the bar is actually displayed. Opening the chat
    # focuses its composer, and a focused text field hides the bar on purpose
    # (it would otherwise sit on the software keyboard) -- a display:none
    # element reports a zero rect, so comparing against it invents an overlap
    # of nearly a whole screen.
    if box["barShown"]:
        assert box["panelBottom"] <= box["barTop"] + 1, (
            f"the chat panel runs under the tab bar by "
            f"{round(box['panelBottom'] - box['barTop'])}px"
        )


@pytest.mark.flaky_e2e
def test_the_bar_is_not_selectable_text(nexora_server, phone_page):
    """Navigation chrome is not text.

    Without a user-select guard, a long press on a slot selects its label
    instead of navigating -- iOS then raises its copy/look-up callout over the
    bar, and dragging across paints all four slots in selection blue, which
    reads as the UI having broken. Reported from a real phone.
    """
    page = phone_page
    _login(page, nexora_server)

    selected = page.evaluate(
        "() => { const bar = document.querySelector('.nx-tabbar');"
        "        const sel = window.getSelection(); sel.removeAllRanges();"
        "        const range = document.createRange();"
        "        range.selectNodeContents(bar); sel.addRange(range);"
        "        return sel.toString().trim(); }"
    )
    assert selected == "", f"the tab bar's labels are selectable: {selected!r}"

    # ...and the same for the sheet's rows, which are the same kind of chrome.
    page.click('[data-testid="mobilenav-more"]')
    page.wait_for_timeout(400)
    item_select = page.evaluate(
        "() => getComputedStyle(document.querySelector("
        "  '#nexora-sidebar .sidebar-nav-item')).userSelect"
    )
    assert item_select == "none", f"sheet rows are selectable: {item_select}"


@pytest.mark.flaky_e2e
def test_the_session_is_rechecked_when_the_app_comes_back(nexora_server, phone_page):
    """An installed app must notice a dead session the moment you look at it.

    The heartbeat polls every 30s, which is fine in a browser tab but not in
    an installed app: iOS suspends timers while the app is backgrounded, so
    reopening it left you on a page from before the phone was locked -- signed
    out without knowing -- until a tick happened to fire. The session is now
    rechecked on resume.
    """
    page = phone_page
    _login(page, nexora_server)
    page.wait_for_timeout(2500)  # let the startup ping go first

    calls = []
    page.on("request", lambda r: calls.append(r.url) if "heartbeat" in r.url else None)

    before = len(calls)
    page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(800)

    assert len(calls) > before, "coming back to the foreground did not recheck the session"


@pytest.mark.flaky_e2e
def test_reporting_rail_fits_without_scrolling_sideways(nexora_server, phone_page):
    """The rail was a side-scrolling strip, because six labelled buttons need
    756px and the row is 358px. That solved the width and created a worse
    problem: dragging left or right on the rail is the same gesture as
    switching view, so the two compete.

    It is a three-column grid now -- no scrolling and no ragged wrap. What made
    the original wrap look broken was six buttons at four different vertical
    positions with dangling connector lines, not the wrapping itself; an even
    3 x 2 reads as deliberate.

    What must not break: every screen reachable without a scroll, and no label
    truncated to get there.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.wait_for_load_state("load")
    page.locator(".rc-rail .rc-nav").first.wait_for(state="visible")
    page.wait_for_timeout(900)

    got = page.evaluate(
        "() => { const rail = document.querySelector('.rc-rail');"
        "        const navs = [...rail.querySelectorAll('.rc-nav')];"
        "        const vw = document.documentElement.clientWidth;"
        "        const vh = window.innerHeight;"
        "        return {count: navs.length,"
        "                scrolls: rail.scrollWidth > rail.clientWidth + 1,"
        "                rows: new Set(navs.map(n =>"
        "                        Math.round(n.getBoundingClientRect().top))).size,"
        "                offScreen: navs.filter(n => {"
        "                    const r = n.getBoundingClientRect();"
        "                    return r.left < -1 || r.right > vw + 1"
        "                           || r.top < 0 || r.bottom > vh + 1; })"
        "                  .map(n => n.innerText.trim().split(String.fromCharCode(10))[0]),"
        "                truncated: navs.filter(n =>"
        "                    n.scrollWidth > n.clientWidth + 1)"
        "                  .map(n => n.innerText.trim().split(String.fromCharCode(10))[0])}; }"
    )
    assert got["count"] >= 4, f"the rail lost screens: {got}"
    assert not got["scrolls"], (
        "the rail scrolls sideways again -- that gesture belongs to switching " "view on a phone"
    )
    assert not got["offScreen"], f"these screens are off the screen: {got['offScreen']}"
    assert not got["truncated"], (
        f"these labels are cut off to make them fit: {got['truncated']} -- a long "
        "one should wrap inside its own button"
    )

    # Reachable without scrolling is the point, so click the last one as-is.
    last = page.locator(".rc-rail .rc-nav").last
    last.click()
    page.wait_for_timeout(900)
    # Assert the class rather than reading the label: the button's text
    # carries a count on its own line, and escaping a newline through to
    # page.evaluate is a trap that has already bitten this file twice.
    assert last.evaluate(
        "e => e.classList.contains('is-active')"
    ), "clicking the last screen did not activate it"


@pytest.mark.parametrize(
    "path", ["/dashboard", "/workitems", "/reporting", "/profile", "/generali-dashboard"]
)
def test_nothing_scrolls_sideways_on_a_phone(nexora_server, phone_page, path):
    """On a phone, left and right belong to moving between views (#368) -- so
    no region inside a page may claim the same gesture.

    This is about elements a finger can actually drag: `overflow-x: auto` or
    `scroll` AND content wider than the box. A clipped overflow cannot be
    dragged, so it does not compete.

    Two offenders when this was written: the reporting rail (756px of content
    in a 358px box) and the workitems status tabs, over by six pixels.
    """
    page = phone_page
    _login(page, nexora_server)
    resp = page.goto(f"{nexora_server}{path}")
    if resp is not None and resp.status >= 400:
        pytest.skip(f"{path} returned {resp.status} for this user")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1800)

    draggable = page.evaluate(
        "() => { const out = [];"
        "        document.querySelectorAll('*').forEach(e => {"
        "          if (!e.getClientRects().length) return;"
        "          const over = e.scrollWidth - e.clientWidth;"
        "          if (over <= 1) return;"
        "          const ox = getComputedStyle(e).overflowX;"
        "          if (ox !== 'auto' && ox !== 'scroll') return;"
        "          out.push({cls: String(e.className).slice(0, 34)"
        "                         || e.tagName.toLowerCase(),"
        "                    id: e.id || null, over});"
        "        });"
        "        return out; }"
    )
    assert not draggable, (
        f"{path} has regions a finger can drag sideways, which fights swiping "
        f"between views: {draggable}"
    )


@pytest.mark.flaky_e2e
def test_reporting_does_not_spend_the_screen_on_chrome(nexora_server, phone_page):
    """Measured before this work: 572px of an 844px phone screen went on chrome
    before the first report -- a 117px topbar, a 161px wrapped rail, a 91px
    screen head and a 48px filter row. Fitting is not designing.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1500)

    top = page.evaluate(
        "() => { const e = document.querySelector('.rc-group-head')"
        "                || document.querySelector('.rs-group-empty-name');"
        "        return e ? Math.round(e.getBoundingClientRect().top) : null; }"
    )
    assert top is not None, "no report group rendered, so nothing to measure"
    assert top < 420, (
        f"the first report starts {top}px down the screen -- the console is "
        "spending the phone on chrome again"
    )


def test_library_search_gets_a_row_of_its_own(nexora_server, phone_page):
    """The Library toolbar put search, sort and the layout toggle on one row.
    Sort and the toggle have intrinsic widths and a text input does not, so
    search collapsed to about the width of its own magnifier -- roughly 20px
    for the one control you type into.

    Search now takes the row, with sort collapsed to a 48px filter button
    beside it, and the two primary actions share a row above at equal widths.
    Also checks the font is at least 16px: below that iOS zooms the page in
    when the field takes focus and leaves the layout scrolled sideways after
    the keyboard closes.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1500)

    got = page.evaluate(
        "() => { const q = s => document.querySelector(s);"
        "        const r = e => e.getBoundingClientRect();"
        "        const row = q('.rc-filter-row'), search = q('#rsSearch');"
        "        const a = q('#rsNewDashboard'), b = q('#rsNewReport');"
        "        return {rowW: Math.round(r(row).width),"
        "                searchW: Math.round(r(search).width),"
        "                searchH: Math.round(r(search).height),"
        "                fontPx: parseFloat(getComputedStyle(search).fontSize),"
        "                sortLeft: Math.round(r(q('.rs-sort-wrap')).left),"
        "                sortW: Math.round(r(q('.rs-sort-wrap')).width),"
        "                searchRight: Math.round(r(search).right),"
        "                toggleShown: !!q('.rc-layout-toggle').getClientRects().length,"
        "                searchTop: Math.round(r(search).top),"
        "                dashW: Math.round(r(a).width), repW: Math.round(r(b).width),"
        "                dashTop: Math.round(r(a).top), repTop: Math.round(r(b).top)}; }"
    )

    # Rect widths are scaled under mobile emulation, so compare rect to rect
    # rather than to a CSS pixel count.
    assert got["searchW"] > got["rowW"] * 0.7, (
        f"search is {got['searchW']}px of a {got['rowW']}px row -- the controls "
        "beside it are eating the width again"
    )
    assert not got["toggleShown"], (
        "the 2-vs-4-per-row toggle is visible on a phone, where the <=900px "
        "block already forces two columns, so it changes nothing and costs the "
        "search its width"
    )
    assert got["sortLeft"] >= got["searchRight"] - 1, (
        f"the filter button (left {got['sortLeft']}px) overlaps the search "
        f"(right {got['searchRight']}px) instead of sitting beside it"
    )
    assert got["sortW"] < got["searchW"], (
        f"the filter button is {got['sortW']}px wide against a {got['searchW']}px "
        "search -- it is still rendering as a full dropdown"
    )
    assert got["fontPx"] >= 16, f"search is {got['fontPx']}px -- iOS will zoom the page in on focus"
    assert got["dashTop"] == got["repTop"], (
        f"New dashboard ({got['dashTop']}px) and New report ({got['repTop']}px) "
        "are on different rows"
    )
    assert (
        abs(got["dashW"] - got["repW"]) <= 2
    ), f"the two actions are unequal: {got['dashW']}px vs {got['repW']}px"


def test_library_card_charts_are_not_clipped_on_a_phone(nexora_server, phone_page):
    """The card preview is a row on a desktop: facts left, chart right. At
    phone width the card is ~150px and the row's fixed parts (facts at 34%, a
    28px gap, a thumb that will not go below 90px) add up to more, so the chart
    ran past the card's right edge and was cut off by `overflow: hidden`.

    Stacking it exposed a second cut: reporting.css pins the preview to a hard
    `height: 78px` and the console rule only raised `min-height`, so the taller
    stacked content clipped from the bottom instead.

    Seeds real reports because an empty Library renders no cards at all, and
    deletes them again -- this runs against the shared INT database.
    """
    page = phone_page
    _login(page, nexora_server)
    token = page.evaluate("() => document.querySelector('meta[name=csrf-token]').content")
    headers = {"X-CSRFToken": token, "Content-Type": "application/json"}
    # No "kind": the list API then calls it "table". The Library drops
    # kind == "sql", so a SQL definition would render nothing to measure.
    defs = [
        (
            "zz-phone-clip-donut",
            {
                "source": "statistics",
                "visualization": "donut",
                "columns": [{"field": "Status"}, {"field": "Total"}],
            },
        ),
        (
            "zz-phone-clip-line",
            {
                "source": "statistics",
                "visualization": "line",
                "columns": [{"field": "CreatedDate", "grain": "month"}, {"field": "Total"}],
            },
        ),
    ]
    made = []
    try:
        for name, defn in defs:
            res = page.request.post(
                f"{nexora_server}/api/reporting/reports",
                headers=headers,
                data={"name": name, "definition": defn},
            )
            assert res.ok, res.text()
            made.append(res.json()["id"])

        page.goto(f"{nexora_server}/reporting")
        page.wait_for_load_state("load")
        page.locator(".rs-card").first.wait_for(state="visible")
        page.wait_for_timeout(600)

        cards = page.evaluate(
            "() => [...document.querySelectorAll('.rs-card')].map(c => {"
            "  const r = e => e.getBoundingClientRect();"
            "  const pv = c.querySelector('.rs-card-preview');"
            "  const sv = c.querySelector('.rs-card-svg');"
            "  const tag = c.querySelector('.rs-card-tag');"
            "  if (!pv || !sv) return null;"
            "  return {name: (c.querySelector('.rs-card-name')||{}).innerText || '',"
            "          overRight: Math.round(r(sv).right - r(c).right),"
            "          overBottom: Math.round(r(sv).bottom - r(pv).bottom),"
            "          badgeTop: Math.round(r(tag).top)};"
            "}).filter(Boolean)"
        )
        assert cards, "no cards with charts rendered, so nothing was measured"
        for c in cards:
            assert c["overRight"] <= 1, (
                f"{c['name']!r}: the chart runs {c['overRight']}px past the card's "
                "right edge, so overflow:hidden cuts it off"
            )
            assert c["overBottom"] <= 1, (
                f"{c['name']!r}: the chart runs {c['overBottom']}px below the "
                "preview box, so its bottom is cut off"
            )
        # A <button> centres its content when the grid stretches it taller than
        # that content, which left one card's badge sitting lower than its
        # neighbour's once previews stopped being a fixed height.
        tops = {c["badgeTop"] for c in cards}
        assert (
            len(tops) <= 1 or max(tops) - min(tops) <= 2
        ), f"cards in a row start their content at different heights: {sorted(tops)}"
    finally:
        for rid in made:
            page.request.delete(f"{nexora_server}/api/reporting/reports/{rid}", headers=headers)


def test_new_report_wizard_fits_a_phone(nexora_server, phone_page):
    """Creating a report was the worst screen on a phone: the step card was a
    232px box floating in the middle of a 320px column with 44px of dead gutter
    either side, and the choices inside it were 186px of a 390px screen. The
    cause was `.rs-wizard-grid`'s `padding: 0 40px 40px`, written for a 1120px
    centred layout and never restated for the console.

    The measure step alone runs about 4,600px of options, so Continue sat that
    far below the option you had just tapped -- you had to scroll past every
    remaining choice to move on. The footer is sticky on a phone now, which is
    what walking the wizard proves: at every step, the button that moves you
    forward is on screen without scrolling.

    Catalogs are stubbed (same helper the reporting suite uses) because the
    measure list is empty without seeded metrics, and an empty list would make
    every assertion below vacuous.
    """
    page = phone_page
    _stub_catalogs(page)
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting?tab=simple")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1200)
    page.get_by_test_id("rs-new-report").click()
    page.locator("#rsWizard").wait_for(state="visible")
    page.locator(".reporting-simple-choice").first.wait_for(state="visible")

    layout = page.evaluate(
        "() => { const q = s => document.querySelector(s);"
        "        const r = e => e.getBoundingClientRect();"
        "        return {cardW: Math.round(r(q('.rs-wizard-stepcard')).width),"
        "                gridW: Math.round(r(q('.rs-wizard-grid')).width),"
        "                choiceW: Math.round(r(q('.reporting-simple-choice')).width),"
        "                closeW: Math.round(r(q('#rsWizardClose')).width),"
        "                scrollW: document.documentElement.scrollWidth,"
        "                vw: document.documentElement.clientWidth}; }"
    )
    # Rect against rect -- these are scaled pixels under mobile emulation.
    assert layout["cardW"] > layout["gridW"] * 0.95, (
        f"the step card is {layout['cardW']}px inside a {layout['gridW']}px column "
        "-- the desktop side padding is back, so it is a small box again"
    )
    assert layout["choiceW"] > layout["cardW"] * 0.8, (
        f"choices are {layout['choiceW']}px in a {layout['cardW']}px card -- they "
        "are packing as pills again instead of full-width rows"
    )
    assert layout["closeW"] < layout["gridW"] * 0.5, (
        f"the close button is {layout['closeW']}px wide -- the Library screen's "
        "equal-halves rule is stretching it into a bar again"
    )
    assert (
        layout["scrollW"] <= layout["vw"] + 1
    ), f"the wizard scrolls sideways: {layout['scrollW']}px in {layout['vw']}px"

    # Four fully labelled step chips need ~495px in a 320px row, so they broke
    # onto two lines with the connectors dangling between them. Only the active
    # step is labelled now, which fits one row.
    rail = page.evaluate(
        "() => { const steps = [...document.querySelectorAll('.rs-rail-step')];"
        "        const tops = new Set(steps.map(e =>"
        "                       Math.round(e.getBoundingClientRect().top)));"
        "        const labelled = steps.filter(e => {"
        "          const t = e.querySelector('.rs-rail-title');"
        "          return t && t.getClientRects().length; }).length;"
        "        return {count: steps.length, rows: tops.size, labelled}; }"
    )
    assert rail["count"] >= 3, f"the step rail lost steps: {rail}"
    assert rail["rows"] == 1, (
        f"the step rail is on {rail['rows']} rows again -- the chips are stacking "
        "two-by-two instead of reading as one progress row"
    )
    assert rail["labelled"] == 1, (
        f"{rail['labelled']} step chips are labelled -- only the current one should "
        "be, or they will not fit a phone row"
    )

    # Walk it. Which steps appear depends on the source (a single-process one
    # skips "Which processes?"), so follow whichever forward button is showing
    # rather than assuming a fixed four.
    forward_ids = ["#rsMeasureNext", "#rsScopeNext", "#rsBreakdownNext", "#rsWizardRun"]
    page.locator(".reporting-simple-choice").first.click()
    page.wait_for_timeout(600)

    seen_any = False
    for _ in range(len(forward_ids)):
        state = page.evaluate(
            "(ids) => { for (const id of ids) {"
            "   const e = document.querySelector(id);"
            "   if (!e || e.hidden || !e.getClientRects().length) continue;"
            "   const r = e.getBoundingClientRect();"
            "   return {id, top: Math.round(r.top),"
            "           onScreen: r.top >= 0 && r.bottom <= window.innerHeight + 1}; }"
            " return null; }",
            forward_ids,
        )
        assert state is not None, "no forward button is showing, so the wizard is a dead end"
        assert state["onScreen"], (
            f"{state['id']} is at {state['top']}px, off the bottom of the screen -- "
            "the footer is not sticking, so you would have to scroll the whole "
            "option list to move on"
        )
        seen_any = True
        if state["id"] == "#rsWizardRun":
            break
        page.click(state["id"])
        page.wait_for_timeout(900)

    assert seen_any, "the wizard never offered a way forward"


def test_dashboard_controls_are_not_stranded_on_a_phone(nexora_server, phone_page):
    """Both dashboard rows end in a block pushed right by `margin-left: auto`
    -- the live clock plus Refresh in the head, the 14/30/90 switch in the
    filter row. On a wide desktop row that is right. On a phone the row wraps
    and the pushed block keeps its right alignment on a line of its own, so it
    sat hard against the right edge with half a row of dead space beside it:
    measured, the range switch started 203px into a 355px row, which is what
    "out of place" looked like.

    Both rows should now use the full content width.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.wait_for_load_state("load")
    page.locator("#dash-range").wait_for(state="visible")
    page.wait_for_timeout(600)

    got = page.evaluate(
        "() => { const q = s => document.querySelector(s);"
        "        const r = e => e.getBoundingClientRect();"
        "        const head = q('.nx-dash-head'), right = q('.nx-dash-head__right');"
        "        const row = q('.nx-dash-filter'), seg = q('#dash-range');"
        "        const btns = [...seg.querySelectorAll('.nx-segmented__btn')]"
        "                       .map(b => Math.round(r(b).width));"
        "        return {headL: Math.round(r(head).left),"
        "                headW: Math.round(r(head).width),"
        "                rightL: Math.round(r(right).left),"
        "                rightW: Math.round(r(right).width),"
        "                rowL: Math.round(r(row).left),"
        "                rowW: Math.round(r(row).width),"
        "                segL: Math.round(r(seg).left),"
        "                segW: Math.round(r(seg).width),"
        "                btns,"
        "                scrollW: document.documentElement.scrollWidth,"
        "                vw: document.documentElement.clientWidth}; }"
    )

    # Rect against rect throughout -- scaled pixels under mobile emulation.
    assert got["rightL"] <= got["headL"] + 2, (
        f"the Updated/Refresh block starts {got['rightL'] - got['headL']}px in from "
        "the page edge -- it is still being pushed right onto its own line"
    )
    assert got["rightW"] > got["headW"] * 0.9, (
        f"that block is {got['rightW']}px of a {got['headW']}px row, so the clock "
        "and Refresh are still bunched at one end"
    )
    assert got["segL"] <= got["rowL"] + 2, (
        f"the 14/30/90 switch starts {got['segL'] - got['rowL']}px into the row -- "
        "stranded against the right edge again"
    )
    assert got["segW"] > got["rowW"] * 0.9, (
        f"the switch is {got['segW']}px of a {got['rowW']}px row rather than " "spanning it"
    )
    assert len(got["btns"]) == 3, f"expected three range buttons, got {got['btns']}"
    assert (
        max(got["btns"]) - min(got["btns"]) <= 3
    ), f"the three range buttons are uneven: {got['btns']}"
    assert (
        got["scrollW"] <= got["vw"] + 1
    ), f"the dashboard scrolls sideways: {got['scrollW']}px in {got['vw']}px"


def test_api_docs_nav_does_not_stick_on_a_phone(nexora_server, phone_page):
    """`.apidocs-nav` is `position: sticky` so the section list stays beside
    the docs while they scroll. Below 900px the layout collapses to one column
    and the nav becomes a full-width block above the text -- sticky then pins
    it to the top of the screen and it rides down over the content it exists to
    navigate. Measured on a phone: 582px tall, 55% of the screen, following
    every scroll.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/api-docs")
    page.wait_for_load_state("load")
    page.locator(".apidocs-nav").wait_for(state="visible")
    page.wait_for_timeout(500)

    assert (
        page.evaluate("() => getComputedStyle(document.querySelector('.apidocs-nav')).position")
        == "static"
    ), "the docs nav is still sticky on a phone"

    before = page.evaluate(
        "() => Math.round(document.querySelector('.apidocs-nav').getBoundingClientRect().top)"
    )
    page.mouse.wheel(0, 1400)
    page.wait_for_timeout(600)
    after = page.evaluate(
        "() => Math.round(document.querySelector('.apidocs-nav').getBoundingClientRect().top)"
    )
    assert after < before - 400, (
        f"the nav barely moved when the page scrolled ({before}px -> {after}px), so "
        "it is still pinned to the screen"
    )

    # Found while fixing the above: the <=900px rule set a bare `1fr`, whose
    # automatic minimum is its content, so a long URL in a code sample took the
    # whole document to 490px in a 390px viewport -- dragging the fixed tab bar
    # with it until its More slot sat off-screen.
    over = page.evaluate(
        "() => ({scrollW: document.documentElement.scrollWidth,"
        "        vw: document.documentElement.clientWidth,"
        "        moreOnScreen: (() => {"
        "          const m = document.querySelector('[data-testid=mobilenav-more]');"
        "          if (!m) return null;"
        "          const r = m.getBoundingClientRect();"
        "          return r.right <= document.documentElement.clientWidth + 1; })()})"
    )
    assert (
        over["scrollW"] <= over["vw"] + 1
    ), f"the docs page scrolls sideways: {over['scrollW']}px in {over['vw']}px"
    assert over["moreOnScreen"], "the tab bar's More slot is pushed off the screen"


def test_api_docs_nav_still_sticks_on_a_narrow_desktop_window(nexora_server, narrow_desktop_page):
    """The other direction of the same gate: a 390px-wide mouse window is a
    snapped or zoomed desktop, and there the sticky nav is the desktop
    behaviour we must not take away.
    """
    page = narrow_desktop_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/api-docs")
    page.wait_for_load_state("load")
    page.locator(".apidocs-nav").wait_for(state="visible")
    page.wait_for_timeout(500)

    assert (
        page.evaluate("() => getComputedStyle(document.querySelector('.apidocs-nav')).position")
        == "sticky"
    ), "a narrow desktop window lost the sticky docs nav -- the gate is matching on width alone"


def test_dashboard_builder_head_fits_a_phone(nexora_server, phone_page):
    """New dashboard's head wrapped into four ragged rows: Back alone, the
    title, then five controls at three different heights -- a 31px "Editing"
    pill, a 36px Add card, 48px buttons -- breaking two-and-two and leaving a
    170px hole after Done.

    The title takes its own row now and the actions pair up two to a row at
    equal widths, so each row ends flush with the head. The pill goes: it only
    shows while editing, which is exactly when the primary button reads
    "Done".
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/reporting")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1500)
    page.click("#rsNewDashboard")
    page.locator(".rdb-head:not(.rl-head)").wait_for(state="visible")
    page.wait_for_timeout(900)

    got = page.evaluate(
        "() => { const q = s => document.querySelector(s);"
        "        const head = q('.rdb-head:not(.rl-head)');"
        "        const hr = head.getBoundingClientRect();"
        "        const acts = [...head.children].filter(e =>"
        "            e.getClientRects().length && /BUTTON/.test(e.tagName)"
        "            && e.id !== 'rdbBack')"
        "          .map(e => { const r = e.getBoundingClientRect();"
        "              return {id: e.id, t: Math.round(r.top),"
        "                      w: Math.round(r.width), h: Math.round(r.height),"
        "                      right: Math.round(r.right)}; });"
        "        const pill = q('#rdbEditingPill');"
        "        return {headRight: Math.round(hr.right),"
        "                headWidth: Math.round(hr.width),"
        "                acts,"
        "                pillShown: pill ? !!pill.getClientRects().length : null,"
        "                scrollW: document.documentElement.scrollWidth,"
        "                vw: document.documentElement.clientWidth}; }"
    )

    assert not got["pillShown"], (
        "the Editing pill is back on a phone -- it repeats what the Done button "
        "already says and costs a row"
    )
    acts = got["acts"]
    assert len(acts) >= 3, f"expected the builder's action buttons, got {acts}"
    for a in acts:
        assert a["h"] >= 44, f"{a['id']} is {a['h']}px tall, under the 44px target"

    # Every row of actions must end flush with the head -- the ragged hole was
    # a row that stopped 170px short.
    rows = {}
    for a in acts:
        rows.setdefault(a["t"], []).append(a)
    for top, row in rows.items():
        widest_gap = got["headRight"] - max(x["right"] for x in row)
        assert widest_gap <= 4, (
            f"the action row at {top}px stops {widest_gap}px short of the head's "
            "right edge, leaving the gap back"
        )
        if len(row) > 1:
            ws = [x["w"] for x in row]
            assert max(ws) - min(ws) <= 3, f"actions on one row are uneven: {ws}"

    assert (
        got["scrollW"] <= got["vw"] + 1
    ), f"the builder scrolls sideways: {got['scrollW']}px in {got['vw']}px"


def test_profile_menu_is_reachable_from_the_sheet(nexora_server, phone_page):
    """#372 -- "all pages on profile are gone": Profile, Appearance, Feedback,
    Help and Sign out were all rendered and clickable, just drawn 176px off
    the left edge of the screen.

    The sidebar's user row opens an el-menu with anchor="right end" as a
    popover. In the 240px desktop sidebar the card lands beside the row; in
    the full-width bottom sheet there is no "beside", and the browser resolved
    the anchor to left: -176px. Sign out being unreachable is the serious half.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.wait_for_load_state("load")
    page.wait_for_timeout(800)

    page.locator('[data-testid="mobilenav-more"]').click()
    _assert_sheet_is_on_screen(page)
    toggle = page.locator('[data-testid="header-profile-toggle"]')
    toggle.scroll_into_view_if_needed()
    toggle.click()
    page.wait_for_timeout(700)

    wanted = [
        "header-profile-link",
        "header-appearance-link",
        "header-feedback-link",
        "header-logout-link",
    ]
    got = page.evaluate(
        "(ids) => { const vw = document.documentElement.clientWidth;"
        "           const vh = window.innerHeight;"
        "           const out = {};"
        "           ids.forEach(id => {"
        "             const e = document.querySelector('[data-testid=' + id + ']');"
        "             if (!e) { out[id] = null; return; }"
        "             const r = e.getBoundingClientRect();"
        "             out[id] = {l: Math.round(r.left), rg: Math.round(r.right),"
        "                        h: Math.round(r.height),"
        "                        onScreen: r.width > 0 && r.left >= 0"
        "                                  && r.right <= vw + 1 && r.top >= 0"
        "                                  && r.bottom <= vh + 1};"
        "           });"
        "           return out; }",
        wanted,
    )
    for tid in wanted:
        box = got[tid]
        assert box is not None, f"{tid} is not in the DOM at all"
        assert box["onScreen"], (
            f"{tid} is off the screen (left {box['l']}, right {box['rg']}) -- the "
            "profile menu is anchored outside the sheet again"
        )
        assert box["h"] >= 44, f"{tid} is {box['h']}px tall, under the 44px target"

    # Reaching it is the point, so prove one actually navigates.
    page.locator('[data-testid="header-profile-link"]').click()
    page.wait_for_load_state("load")
    assert page.url.endswith("/profile"), f"Your profile went to {page.url}"


@pytest.mark.parametrize(
    "path", ["/workitems", "/profile", "/appearance", "/reporting", "/dashboard"]
)
def test_text_fields_do_not_zoom_ios_in(nexora_server, phone_page, path):
    """#369 -- "search button breaks page design (it zooms everything out)".

    Safari zooms the page in when a focused field's font is under 16px, and it
    does not zoom back out when the keyboard closes: you are left on a layout
    twice its intended size, scrolled sideways. Measured offenders were the
    workitems search at 12.5px, .nx-input at 13px on /appearance and the
    Generali date pickers, and .profile-input at 14px across six fields.

    Only types that open a keyboard count -- a checkbox does not zoom.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}{path}")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1200)

    small = page.evaluate(
        "() => { const TYPES = ['text','search','email','password','tel','url',"
        "            'number','date','datetime-local','month','time','week'];"
        "        const out = [];"
        "        document.querySelectorAll('input, textarea').forEach(e => {"
        "          if (e.tagName === 'INPUT'"
        "              && !TYPES.includes((e.type || 'text').toLowerCase())) return;"
        "          if (!e.getClientRects().length) return;"
        "          const fs = parseFloat(getComputedStyle(e).fontSize);"
        "          if (fs >= 16) return;"
        "          out.push({cls: String(e.className).trim().slice(0, 40),"
        "                    id: e.id || null, px: fs});"
        "        });"
        "        return out; }"
    )
    assert not small, (
        f"{path} has text fields under 16px, so iOS will zoom the page in when "
        f"they take focus: {small}"
    )


def test_the_top_strip_follows_the_theme(nexora_server, phone_page):
    """#370 -- "the top part is stuck in darkmode".

    Two things that live outside the stylesheet decide the colour above the
    page: the theme-color meta, and the inline background the pre-paint script
    puts on <html> to avoid a flash. Both were written once, before paint, and
    never updated -- so switching to light mode left <html> painted #0f172a
    while the body went light. With viewport-fit=cover the html canvas is what
    shows through the safe areas, which is the strip behind the status bar. An
    inline style also beats any stylesheet rule, so CSS could not fix it.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.wait_for_load_state("load")
    page.wait_for_timeout(800)

    def state():
        return page.evaluate(
            "() => { const m = document.querySelector('meta[name=theme-color]');"
            "        const root = document.documentElement;"
            "        return {dark: root.classList.contains('dark'),"
            "                meta: m ? m.getAttribute('content') : null,"
            "                htmlBg: root.style.backgroundColor,"
            "                bodyBg: getComputedStyle(document.body)"
            "                          .backgroundColor}; }"
        )

    page.locator('[data-testid="mobilenav-more"]').click()
    page.wait_for_timeout(600)
    toggle = page.locator('[data-testid="header-dark-mode-toggle"]')
    toggle.scroll_into_view_if_needed()

    seen = []
    for _ in range(2):
        toggle.click()
        page.wait_for_timeout(700)
        seen.append(state())

    assert {s["dark"] for s in seen} == {
        True,
        False,
    }, f"the toggle did not actually change the theme: {seen}"
    for st in seen:
        want = "#0f172a" if st["dark"] else "#f9fafb"
        assert st["meta"] == want, (
            f"theme-color is {st['meta']} while dark={st['dark']} -- the browser's "
            "top strip is showing the other theme's colour"
        )
        # The pre-paint script sets this inline; if it is set at all it must
        # match, because it is what paints the safe areas.
        if st["htmlBg"]:
            assert st["htmlBg"] == st["bodyBg"], (
                f"<html> is painted {st['htmlBg']} while the body is "
                f"{st['bodyBg']} (dark={st['dark']}) -- the strip behind the "
                "status bar is stuck on the old theme"
            )


def test_workitems_overview_spends_less_of_the_phone_on_chrome(nexora_server, phone_page):
    """#362 / #364 -- the overview stacked every filter into its own full-width
    row and broke the three action buttons 2 + 1, which put roughly 640px of
    chrome above the first workitem on an 844px screen: measured, the first row
    started at 809px, i.e. under the tab bar.

    Search now takes a row, the process picker and the stage filter share the
    next, and the actions are one scrolling toolbar. Measured after: filter
    399px -> 179px, actions 106px -> 48px, first row 809px -> 532px.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.wait_for_load_state("load")
    page.wait_for_timeout(2000)

    got = page.evaluate(
        "() => { const q = s => document.querySelector(s);"
        "        const h = e => e ? Math.round(e.getBoundingClientRect().height) : null;"
        "        const filter = q('.nx-wi-filter'), actions = q('.nx-wi-actions');"
        "        const search = q('.nx-wi-search');"
        "        const scope = q('.nx-wi-filter > .nx-scope');"
        "        const stage = q('[data-testid=workitems-stage-filter]');"
        "        const r = e => e ? e.getBoundingClientRect() : null;"
        "        const row = q('tbody tr');"
        "        return {filterH: h(filter), actionsH: h(actions),"
        "                firstRowTop: row"
        "                  ? Math.round(row.getBoundingClientRect().top) : null,"
        "                searchW: search ? Math.round(r(search).width) : null,"
        "                filterW: filter ? Math.round(r(filter).width) : null,"
        "                scopeTop: scope ? Math.round(r(scope).top) : null,"
        "                stageTop: stage ? Math.round(r(stage).top) : null,"
        "                searchTop: search ? Math.round(r(search).top) : null,"
        "                actionsScrollable: actions"
        "                  ? actions.scrollWidth > actions.clientWidth + 1 : null,"
        "                actionsTruncated: actions"
        "                  ? [...actions.querySelectorAll('.nx-btn')]"
        "                      .filter(x => x.scrollWidth > x.clientWidth + 1)"
        "                      .map(x => x.innerText.trim().slice(0, 18)) : [],"
        "                actionRows: actions"
        "                  ? new Set([...actions.children]"
        "                      .filter(e => e.getClientRects().length)"
        "                      .map(e => Math.round(e.getBoundingClientRect().top))).size"
        "                  : null,"
        "                scrollW: document.documentElement.scrollWidth,"
        "                vw: document.documentElement.clientWidth}; }"
    )

    # Was "must be exactly one row", which described the side-scrolling strip
    # this replaced. The strip claimed the left-right gesture that belongs to
    # switching views (#368), so the actions are a three-column grid now. An
    # even grid row is fine; what must not come back is the draggable strip or
    # a label truncated to fit one.
    assert not got["actionsScrollable"], (
        "the action toolbar scrolls sideways again -- that gesture belongs to "
        "switching view on a phone"
    )
    assert got["actionRows"] <= 2, (
        f"the actions are on {got['actionRows']} rows -- a three-column grid "
        "should need at most two"
    )
    assert not got["actionsTruncated"], (
        f"these action labels are cut off to make them fit: "
        f"{got['actionsTruncated']} -- a long one should wrap inside its button"
    )
    assert got["filterH"] < 260, (
        f"the filter block is {got['filterH']}px tall -- it is back to a column "
        "of full-width rows"
    )
    # Search owns its row; the two pickers share the one below it.
    assert got["searchW"] > got["filterW"] * 0.9, (
        f"search is {got['searchW']}px of a {got['filterW']}px row, so it is "
        "sharing with something again"
    )
    assert got["scopeTop"] == got["stageTop"], (
        f"the process picker ({got['scopeTop']}px) and the stage filter "
        f"({got['stageTop']}px) are not sharing a row"
    )
    assert (
        got["searchTop"] < got["scopeTop"]
    ), "search should sit above the two pickers, not below them"
    assert got["firstRowTop"] is not None, "no workitem rows rendered, so nothing to measure"
    assert (
        got["firstRowTop"] < 620
    ), f"the first workitem starts {got['firstRowTop']}px down an 844px screen"
    assert (
        got["scrollW"] <= got["vw"] + 1
    ), f"the overview scrolls sideways: {got['scrollW']}px in {got['vw']}px"


def test_workitem_stage_indicator_gets_its_own_line(nexora_server, phone_page):
    """#363 -- each row is a card, and every cell is one flex line spread by
    `space-between`. The Workitem cell holds two values, the id and the stage
    indicator, so the label, the id, the four ticks and the stage name all
    shared one 355px line: "WORKITEM 18995 - - - Validation", with the pair
    crushed into 131px at the right edge.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.wait_for_load_state("load")
    page.locator("tbody tr").first.wait_for(state="visible")
    page.wait_for_timeout(600)

    got = page.evaluate(
        "() => { const cell = document.querySelector('.nx-wi-cell-stage');"
        "        if (!cell) return null;"
        "        const td = cell.closest('td');"
        "        const id = td.querySelector('.nx-wi-cell-id');"
        "        const r = e => e.getBoundingClientRect();"
        "        const tick = cell.querySelector('.nx-wi-tick');"
        "        return {stageW: Math.round(r(cell).width),"
        "                tdW: Math.round(r(td).width),"
        "                stageTop: Math.round(r(cell).top),"
        "                idTop: Math.round(r(id).top),"
        "                tickH: tick ? Math.round(r(tick).height) : null}; }"
    )
    if got is None:
        # The indicator only renders for a workitem that has a stage, and the
        # seeded rows here may not. Skipping is honest: there is nothing to
        # measure. It is exercised against INT data, where stages exist.
        pytest.skip("no workitem in this environment carries a stage indicator")
    assert got["stageTop"] > got["idTop"], (
        f"the stage indicator is on the same line as the id (both around "
        f"{got['idTop']}px) -- it is being crushed to the right again"
    )
    assert got["stageW"] > got["tdW"] * 0.8, (
        f"the stage indicator is {got['stageW']}px of a {got['tdW']}px cell "
        "rather than having the line to itself"
    )


# A swipe, dispatched as touch events at chosen coordinates. Hand-dragging a
# mouse in a headed browser is not reproducible; this exercises each rule on
# purpose. `touches` is empty on touchend because the finger has lifted --
# reading e.touches there is the classic mistake, so the fixture models it.
_SWIPE = """
([x1, y1, x2, y2]) => {
  const target = document.elementFromPoint(x1, y1) || document.body;
  const mk = (type, x, y) => {
    const t = new Touch({identifier: 1, target,
                         clientX: x, clientY: y, screenX: x, screenY: y});
    return new TouchEvent(type, {bubbles: true, cancelable: true,
                                 touches: type === 'touchend' ? [] : [t],
                                 changedTouches: [t]});
  };
  target.dispatchEvent(mk('touchstart', x1, y1));
  target.dispatchEvent(mk('touchend', x2, y2));
}
"""


def _swipe(page, x1, y1, x2, y2):
    """One swipe, then long enough for a navigation to settle.

    The wait is deliberately generous: /reporting takes about three seconds to
    boot, and a shorter wait made this look like the swipe had been ignored
    when it had actually worked -- a false failure that cost real time.
    """
    page.evaluate(_SWIPE, [x1, y1, x2, y2])
    page.wait_for_timeout(3200)
    return page.url


def test_swiping_moves_between_the_bar_s_views(nexora_server, phone_page):
    """#368 -- a swipe across the middle of the screen moves to the next view.

    The order comes from the tab bar itself, whose slots are permission-
    filtered links built from the sidebar's own nav_items, so there is no
    second list of pages to drift out of step. It also means a user scoped to
    one tenant swipes between that tenant's pages with no extra code.

    No wrap at the ends: arriving back at the first view from the last reads
    as having gone the wrong way, with no cue that you looped.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1200)

    slots = page.evaluate(
        "() => [...document.querySelectorAll('.nx-tabbar a.nx-tabbar-item')]"
        "        .map(a => a.getAttribute('href'))"
    )
    if len(slots) < 3:
        pytest.skip(f"this user has {len(slots)} swipeable views; need 3")

    # Left pulls the next view in, the way a page turns.
    assert "/reporting" in _swipe(
        page, 300, 400, 100, 410
    ), "swiping left from the first view did not reach the second"
    assert "/workitems" in _swipe(
        page, 300, 400, 100, 410
    ), "swiping left again did not reach the third view"
    # And back.
    assert "/reporting" in _swipe(page, 100, 400, 300, 410), "swiping right did not go back a view"
    assert "/dashboard" in _swipe(
        page, 100, 400, 300, 410
    ), "swiping right did not return to the first view"
    # Off the end: stays put.
    assert "/dashboard" in _swipe(
        page, 100, 400, 300, 410
    ), "swiping right past the first view wrapped around to the last"


def test_swipe_leaves_the_edges_to_the_browser(nexora_server, phone_page):
    """The outer 30px belong to the platform's back/forward gesture, which in
    an installed app is the ONLY way back out of a page -- there is no browser
    chrome to press. Taking it would trap people, and Safari ignores attempts
    to suppress it anyway.

    Also checks the two cheaper exclusions: a drag that travelled further
    vertically than horizontally is a scroll (a thumb pivots at the joint, so
    every scroll drifts sideways), and a short drag is a sloppy tap.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1200)

    start = page.url
    assert _swipe(page, 10, 400, 260, 410) == start, (
        "a swipe starting 10px from the edge navigated -- that gesture belongs "
        "to the browser's back/forward"
    )
    assert (
        _swipe(page, 200, 600, 140, 200) == start
    ), "a drag of 400px up and 60px sideways navigated -- that is a scroll"
    assert (
        _swipe(page, 200, 400, 160, 405) == start
    ), "a 40px swipe navigated -- under the distance threshold"


def test_view_transitions_are_opted_in_on_a_phone(nexora_server, phone_page):
    """The white flash between page loads is the one thing that gives an
    installed nexora away as a web page -- and it is not slowness. Measured on
    dev: 16-68ms to first byte with 3-9KB over the wire, because everything
    else is cached. The seam is the browser rebuilding the page.

    `@view-transition` hides it with no JavaScript. Both the page you leave and
    the page you arrive at must carry the rule, which is why it lives in the
    globally loaded sheet.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.wait_for_load_state("load")
    page.wait_for_timeout(900)

    got = page.evaluate(
        "() => { let cond = null, reduced = 0;"
        "        for (const sh of document.styleSheets) {"
        "          let rules; try { rules = sh.cssRules; } catch (e) { continue; }"
        "          for (const r of rules) {"
        "            if (r.constructor.name === 'CSSMediaRule') {"
        "              for (const i of r.cssRules) {"
        "                if (i.constructor.name === 'CSSViewTransitionRule')"
        "                  cond = r.conditionText;"
        "              }"
        "            }"
        "            if ((r.cssText || '').includes('view-transition-group'))"
        "              reduced++;"
        "          }"
        "        }"
        "        return {cond, reduced,"
        "                matches: cond ? matchMedia(cond).matches : null}; }"
    )
    assert got["cond"], "no @view-transition opt-in reached the page"
    assert got["matches"], f"the opt-in is gated on {got['cond']!r}, which does not match a phone"
    assert got["reduced"] >= 2, (
        "reduced motion has no way to cancel the animation -- a transition "
        "cannot be half-off, so the animation must be switched off rather than "
        f"the opt-in removed (found {got['reduced']} rules)"
    )


def test_view_transitions_stay_off_on_a_narrow_desktop_window(nexora_server, narrow_desktop_page):
    """The other direction of the gate. A 390px mouse window is a snapped or
    zoomed desktop, where the page sits in browser chrome and nobody expects
    app-style transitions between navigations.
    """
    page = narrow_desktop_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/dashboard")
    page.wait_for_load_state("load")
    page.wait_for_timeout(900)

    matches = page.evaluate(
        "() => { for (const sh of document.styleSheets) {"
        "          let rules; try { rules = sh.cssRules; } catch (e) { continue; }"
        "          for (const r of rules) {"
        "            if (r.constructor.name !== 'CSSMediaRule') continue;"
        "            for (const i of r.cssRules) {"
        "              if (i.constructor.name === 'CSSViewTransitionRule')"
        "                return matchMedia(r.conditionText).matches;"
        "            }"
        "          }"
        "        }"
        "        return null; }"
    )
    assert matches is False, (
        f"view transitions apply to a narrow desktop window (matches={matches}) "
        "-- the gate is keying on width alone"
    )


def _bar_shown(page):
    return page.evaluate(
        "() => { const b = document.querySelector('.nx-tabbar');"
        "        return b ? getComputedStyle(b).display !== 'none' : null; }"
    )


@pytest.mark.flaky_e2e
def test_the_bar_yields_to_the_software_keyboard(nexora_server, phone_page):
    """With `interactive-widget=resizes-content` the layout viewport shrinks
    when the keyboard opens, so bottom-anchored things sit above it rather than
    behind it -- which is what makes Eddard's composer visible while you type
    into it. The trade is that the tab bar would then sit on the keyboard,
    taking a row of what little height is left, so it hides while a field has
    focus.

    Playwright has no software keyboard, so this tests the condition the rule
    actually keys off -- a text field holding focus -- and the two things that
    would make it wrong.
    """
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.wait_for_load_state("load")
    page.wait_for_timeout(800)

    assert _bar_shown(page), "the bar should be visible at rest"

    search = page.locator('[data-testid="workitems-search"]')
    search.focus()
    page.wait_for_timeout(250)
    assert not _bar_shown(page), "the bar should get out of the way of the keyboard"

    search.blur()
    page.wait_for_timeout(250)
    assert _bar_shown(page), "the bar must come back when the field loses focus"


@pytest.mark.flaky_e2e
def test_controls_that_open_no_keyboard_keep_the_bar(nexora_server, phone_page):
    """Tapping a checkbox or a select must not make the navigation vanish --
    neither opens a keyboard, and losing the nav for them would be a bug, not
    a feature."""
    page = phone_page
    _login(page, nexora_server)
    page.goto(f"{nexora_server}/workitems")
    page.wait_for_load_state("load")
    page.wait_for_timeout(1200)

    for selector, what in (('input[type="checkbox"]', "a checkbox"), ("select", "a select")):
        el = page.locator(selector).first
        if not el.count():
            continue
        el.focus()
        page.wait_for_timeout(250)
        assert _bar_shown(page), f"focusing {what} hid the navigation"


@pytest.mark.flaky_e2e
def test_the_layout_resizes_for_the_keyboard(nexora_server, phone_page):
    """The viewport opt-in this depends on. Without it the layout viewport does
    not shrink and anything at `bottom: 0` -- the bar, and Eddard's composer --
    ends up behind the keyboard."""
    page = phone_page
    _login(page, nexora_server)
    content = page.evaluate("() => document.querySelector('meta[name=viewport]').content")
    assert "interactive-widget=resizes-content" in content, content
    # and the inset opt-in from the home-indicator work, same tag
    assert "viewport-fit=cover" in content, content


@pytest.mark.flaky_e2e
def test_the_bar_shows_focus_for_a_keyboard(nexora_server, phone_page):
    """A touch device can still have a keyboard -- an iPad with a Magic
    Keyboard reports `pointer: coarse` and Tabs like anything else. The slots
    were relying on the browser's default hairline outline, near-invisible
    against the bar's own background."""
    page = phone_page
    _login(page, nexora_server)
    page.wait_for_timeout(600)

    slot = page.locator('[data-testid="mobilenav-more"]')
    slot.focus()
    page.wait_for_timeout(200)
    ring = page.evaluate(
        "() => { const cs = getComputedStyle("
        "          document.querySelector('[data-testid=\"mobilenav-more\"]'));"
        "        return {style: cs.outlineStyle,"
        "                width: parseFloat(cs.outlineWidth) || 0}; }"
    )
    assert ring["style"] != "none", "the focused slot has no outline at all"
    # scaled px under mobile emulation, so compare generously against a hairline
    assert ring["width"] > 1.2, f"the focus ring is a hairline: {ring}"
