r"""The phone tab bar follows the tenant you are actually in.

The bar had two branches: a ``tenant_solo`` user got their tenant's pages,
and everybody else got the three Global entries. Staff who can see more than
one tenant fell into "everybody else" and kept the Global bar **even while
standing on a tenant page** -- so on `/generali/documents` the bar read
Dashboard / Reporting / Workitems with **no slot lit at all**. That is worse
than it looks: `static/js/swipe_nav.js` finds its position by looking for the
active slot, so with none lit, swiping between views did nothing on every one
of those pages. The bar was dead weight exactly where the user was working.

These are integration tests, not e2e, for two reasons: the bar is entirely
server-rendered, so the HTML is the whole truth; and the TEST database has no
Generali tenant (the e2e suite skips those pages with a 403), so the registry
has to be faked either way. Faking it here is honest -- faking it in a browser
test would only be slower.

The fake page dicts match ``nx_lib/views/tenant.py::_tenant_nav_page``
exactly, including the asymmetry that matters: a **custom** page carries
``endpoint``/``active``/``icon`` and a **list** page does not. A fake that
smoothed that over would pass while the template's two branches rotted.
"""

import sys
import types

import nx_lib.views.tenant as tv

# `nx_lib.tenant.__init__` re-exports a FUNCTION called `registry`, which
# shadows the submodule of the same name -- so "nx_lib.tenant.registry.X" as a
# monkeypatch target resolves to the function and raises. The module itself is
# still in sys.modules, and `_inject_tenant_nav` does its
# `from .tenant.registry import organization_tenant` at call time, so patching
# the attribute there is what actually takes effect.
_registry_mod = sys.modules["nx_lib.tenant.registry"]

TENANT_CODE = "acme"
ACTIVE_ON_DASHBOARD = f"tenant_{TENANT_CODE}_dashboard"


def _list_page(key, label):
    """A registry list/crud page: no endpoint, no icon, no active key."""
    return {
        "key": key,
        "page_type": "list",
        "endpoint": None,
        "url": f"/t/{TENANT_CODE}/{key}",
        "label": label,
    }


def _custom_page(key, label, active):
    """A registry 'custom' page: carries endpoint, icon and its own `active`.

    `endpoint` is deliberately NOT equal to `active`, which is what sends the
    template down its `(active_page == p.active)` branch -- the other branch
    compares against `tenant_scoped`, which is None for staff.
    """
    return {
        "key": key,
        "page_type": "custom",
        "endpoint": f"ep_{key}",
        "url": f"/t/{TENANT_CODE}/{key}",
        "label": label,
        "icon": "fa-table-list",
        "active": active,
    }


def _nav(pages, code=TENANT_CODE, label="Acme"):
    return [{"code": code, "label": label, "pages": pages}]


FIVE_PAGES = [
    _list_page("alpha", "Alpha"),
    _list_page("bravo", "Bravo"),
    _list_page("charlie", "Charlie"),
    _list_page("delta", "Delta"),
    _list_page("echo", "Echo"),
]


def _acme(code):
    return types.SimpleNamespace(code=code, display_name="Acme", active=True)


def _staff_in_acme(monkeypatch, pages=FIVE_PAGES):
    """A staff user (no tenant of their own) who can view the acme tenant."""
    monkeypatch.setattr(tv, "tenant", _acme)
    monkeypatch.setattr(tv, "can_view_tenant", lambda code: True)
    monkeypatch.setattr(tv, "visible_tenant_nav", lambda: _nav(pages))
    monkeypatch.setattr(tv, "organization_tenant", lambda org: None)
    monkeypatch.setattr(_registry_mod, "organization_tenant", lambda org: None)
    monkeypatch.setattr("nx_lib.process_helpers.tenant_processes", lambda code: set())


def _slots(html):
    """The bar's page slots, in order, as (testid-suffix, href) pairs.

    Reads the rendered bar rather than any template internal, which is the
    same contract swipe_nav.js relies on.
    """
    import re

    return re.findall(
        r'<a href="([^"]+)"[^>]*class="nx-tabbar-item[^"]*"[^>]*'
        r'data-testid="mobilenav-slot-([^"]+)"',
        html,
        re.S,
    )


def _bar(html):
    """Just the <nav class="nx-tabbar"> ... </nav> section."""
    start = html.index('<nav class="nx-tabbar"')
    return html[start : html.index("</nav>", start)]


def test_bar_follows_the_scoped_tenant(user_client, monkeypatch):
    """Standing in a tenant, the bar carries that tenant's pages."""
    _staff_in_acme(monkeypatch)

    resp = user_client.get(f"/dashboard?tenant={TENANT_CODE}")
    assert resp.status_code == 200
    bar = _bar(resp.data.decode())

    hrefs = [href for href, _ in _slots(bar)]
    assert hrefs, "the bar rendered no page slots at all"
    assert all(h.startswith(f"/t/{TENANT_CODE}/") for h in hrefs), (
        "the bar is still showing the Global entries while scoped to a tenant; " f"got {hrefs}"
    )


def test_bar_keeps_the_global_entries_when_not_scoped(user_client, monkeypatch):
    """A staff user who has not picked a tenant keeps exactly today's bar."""
    _staff_in_acme(monkeypatch)

    # The Global sidebar entry sends an explicit empty tenant, which clears the
    # scope (see apply_tenant_scope).
    resp = user_client.get("/dashboard?tenant=")
    assert resp.status_code == 200
    bar = _bar(resp.data.decode())

    hrefs = [href for href, _ in _slots(bar)]
    assert hrefs, "the bar rendered no page slots at all"
    assert not any(
        h.startswith(f"/t/{TENANT_CODE}/") for h in hrefs
    ), f"an unscoped staff user should keep the Global bar; got {hrefs}"


def test_more_button_is_still_there_and_is_not_a_page_slot(user_client, monkeypatch):
    """'More' stays pinned and never becomes one of the page slots.

    swipe_nav.js navigates between `a.nx-tabbar-item` only; More is a
    <button> precisely so it is not a destination. If it ever rendered as a
    slot, swiping would try to 'navigate' to the sheet.
    """
    _staff_in_acme(monkeypatch)

    bar = _bar(user_client.get(f"/dashboard?tenant={TENANT_CODE}").data.decode())
    assert 'id="nx-tabbar-more"' in bar
    assert "mobilenav-slot-more" not in bar


# ------------------------------------------------- the three-slot window --

# Five pages with the FOURTH one active (index 3). A three-wide window centred
# on it is pages[2:5] -- charlie, delta, echo -- with delta in the middle.
# ACTIVE_ON_DASHBOARD is what templates/dashboard.html actually sets while
# scoped to a tenant:
#   {% set active_page = ('tenant_' ~ dashboard_tenant.code ~ '_dashboard')
#                        if dashboard_tenant else 'dashboard' %}
# Giving a custom page that value makes it the active slot on /dashboard,
# without needing the real tenant_page route and a stubbed registry.
WINDOW_PAGES = [
    _custom_page("alpha", "Alpha", "ep_alpha_active"),
    _custom_page("bravo", "Bravo", "ep_bravo_active"),
    _custom_page("charlie", "Charlie", "ep_charlie_active"),
    _custom_page("delta", "Delta", ACTIVE_ON_DASHBOARD),
    _custom_page("echo", "Echo", "ep_echo_active"),
]


def test_window_centres_the_active_page(user_client, monkeypatch):
    """Three slots, the active page in the middle, clamped at the ends.

    Without this the bar renders pages[:3], so the fourth page of five lights
    nothing -- and swipe_nav.js, which locates itself by the active slot, does
    nothing on that page.
    """
    _staff_in_acme(monkeypatch, pages=WINDOW_PAGES)

    html = user_client.get(f"/dashboard?tenant={TENANT_CODE}").data.decode()
    bar = _bar(html)
    keys = [key for _, key in _slots(bar)]

    assert keys == [
        "charlie",
        "delta",
        "echo",
    ], f"expected a window centred on the active 4th page; got {keys}"
    # and the middle one is the lit one
    assert 'aria-current="page"' in bar
    active_at = [i for i, (_, k) in enumerate(_slots(bar)) if k == "delta"]
    assert active_at == [1], f"the active page should be the middle slot; got index {active_at}"


def test_window_clamps_at_the_first_page(user_client, monkeypatch):
    """On the first page there is no 'previous', so the window cannot slide
    left past it -- it shows the first three and no wrap happens."""
    pages = list(WINDOW_PAGES)
    pages[3] = _custom_page("delta", "Delta", "ep_delta_active")
    pages[0] = _custom_page("alpha", "Alpha", ACTIVE_ON_DASHBOARD)
    _staff_in_acme(monkeypatch, pages=pages)

    bar = _bar(user_client.get(f"/dashboard?tenant={TENANT_CODE}").data.decode())
    keys = [key for _, key in _slots(bar)]
    assert keys == ["alpha", "bravo", "charlie"], f"got {keys}"


def test_window_clamps_at_the_last_page(user_client, monkeypatch):
    """Likewise at the end: the last window is the final three, not a wrap."""
    pages = list(WINDOW_PAGES)
    pages[3] = _custom_page("delta", "Delta", "ep_delta_active")
    pages[4] = _custom_page("echo", "Echo", ACTIVE_ON_DASHBOARD)
    _staff_in_acme(monkeypatch, pages=pages)

    bar = _bar(user_client.get(f"/dashboard?tenant={TENANT_CODE}").data.decode())
    keys = [key for _, key in _slots(bar)]
    assert keys == ["charlie", "delta", "echo"], f"got {keys}"


def test_window_renders_all_of_a_short_list(user_client, monkeypatch):
    """Fewer than three pages is not a special case -- render what there is."""
    _staff_in_acme(monkeypatch, pages=WINDOW_PAGES[:2])

    bar = _bar(user_client.get(f"/dashboard?tenant={TENANT_CODE}").data.decode())
    assert [key for _, key in _slots(bar)] == ["alpha", "bravo"]


# ------------------------------------------------ the phone tenant switcher --


def _two_tenants(monkeypatch):
    other = {"code": "other", "label": "Other Co", "pages": [_list_page("zulu", "Zulu")]}
    _staff_in_acme(monkeypatch)
    monkeypatch.setattr(tv, "visible_tenant_nav", lambda: [*_nav(FIVE_PAGES), other])


def test_sheet_offers_a_chip_per_tenant(user_client, monkeypatch):
    _two_tenants(monkeypatch)
    html = user_client.get("/dashboard").data.decode()
    assert 'data-testid="tenant-switcher"' in html
    assert 'data-testid="tenant-switch-acme"' in html
    assert 'data-testid="tenant-switch-other"' in html


def test_chips_link_a_real_page_not_a_tenant_query(user_client, monkeypatch):
    """`?tenant=` is only honoured by routes calling apply_tenant_scope."""
    import re

    _two_tenants(monkeypatch)
    html = user_client.get("/dashboard").data.decode()
    hrefs = re.findall(r'<a href="([^"]+)"[^>]*class="nx-tenant-chip', html)
    assert hrefs, "no chips rendered"
    assert all(not h.startswith("?tenant=") for h in hrefs), hrefs


def test_a_solo_tenant_user_gets_no_switcher_and_is_never_told_the_name(user_client, monkeypatch):
    """#255: for a member the tenant IS the portal, so the UI never names it."""
    _staff_in_acme(monkeypatch)
    monkeypatch.setattr(tv, "organization_tenant", lambda org: TENANT_CODE)
    monkeypatch.setattr(_registry_mod, "organization_tenant", lambda org: TENANT_CODE)

    html = user_client.get("/dashboard").data.decode()
    assert 'data-testid="tenant-switcher"' not in html
    assert "Acme" not in html


def test_one_tenant_is_not_a_choice(user_client, monkeypatch):
    _staff_in_acme(monkeypatch)  # a single tenant in the nav
    html = user_client.get("/dashboard").data.decode()
    assert 'data-testid="tenant-switcher"' not in html


def test_rendered_slots_carry_distinct_view_transition_names(user_client, monkeypatch):
    """Named per page, so the browser slides a slot to its new position.

    Duplicates inside one document would make the transition invalid, so the
    distinctness matters as much as the naming.
    """
    import re

    _staff_in_acme(monkeypatch, pages=WINDOW_PAGES)
    bar = _bar(user_client.get(f"/dashboard?tenant={TENANT_CODE}").data.decode())
    names = re.findall(r"view-transition-name:\s*([a-z0-9-]+)", bar)

    assert "nx-tab-more" in names, "More must be anchored across the transition"
    slots = [n for n in names if n != "nx-tab-more"]
    assert slots == ["nx-tab-charlie", "nx-tab-delta", "nx-tab-echo"], slots
    assert len(set(names)) == len(names), f"duplicate transition names: {names}"
