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
