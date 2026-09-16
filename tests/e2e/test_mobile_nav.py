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
        "                headTop: hr.top, headBottom: hr.bottom, barTop: tr.top}; }"
    )
    assert box, "chat panel, its header, or the tab bar is missing"
    assert box["headTop"] >= 0, (
        f"the chat header is off the top of the screen ({box['headTop']}px) -- "
        "its close button is unreachable"
    )
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
