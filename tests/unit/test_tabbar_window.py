r"""The phone tab bar's three slots: which tenant, and which page is lit.

Pure-function tests for `nx_lib/tabbar.py`. The behaviour these pin down was
found by standing on a real Generali page and watching the bar show another
tenant's pages with nothing lit -- see the module docstring there for why the
session's tenant scope is the wrong thing to key on.

The fake page dicts mirror `nx_lib/views/tenant.py::_tenant_nav_page`,
including the asymmetry that caused the bug: a **custom** page carries
`endpoint` and `active`, a **list** page carries neither.
"""

from nx_lib.tabbar import tabbar_window, window_start


def custom(key, active, endpoint=None):
    return {
        "key": key,
        "page_type": "custom",
        "endpoint": endpoint or f"ep_{key}",
        "url": f"/{key}",
        "label": key.title(),
        "icon": "fa-table-list",
        "active": active,
    }


def listpage(key):
    return {"key": key, "page_type": "list", "endpoint": None, "url": f"/{key}", "label": key}


def tenant(code, pages, label=None):
    return {"code": code, "label": label or code.title(), "pages": pages}


# Generali's real shape: eight custom pages, several of whose `active` value
# equals their `endpoint` -- which is exactly the case that used to fail.
GENERALI = tenant(
    "generali",
    [
        custom("dashboard", "generali_dashboard", endpoint="generali_evaluation"),
        custom("documents", "generali_documents", endpoint="generali_documents"),
        custom("reporting", "generali_reporting", endpoint="generali_reporting"),
        custom("additional-services", "generali_additionalservices"),
        custom("base-services", "generali_baseservices"),
        custom("project-management", "generali_projectmanagement"),
        custom("pdqm", "generali_pdqm", endpoint="generali_pdqm"),
        custom("import-status", "generali_importstatus"),
    ],
)


def keys(slots):
    return [p["key"] for p, _ in slots]


def lit(slots):
    return [p["key"] for p, on in slots if on]


# ----------------------------------------------------------- which tenant --


def test_finds_the_tenant_whose_page_is_on_screen():
    slots = tabbar_window([GENERALI], "generali_pdqm")
    assert lit(slots) == ["pdqm"]


def test_matches_even_when_active_equals_endpoint():
    """The three pages that used to fail.

    `documents`, `reporting` and `pdqm` all have active == endpoint, which sent
    the old template down a guard written for shared endpoints and left the
    bar showing another tenant entirely.
    """
    for key, active in [
        ("documents", "generali_documents"),
        ("reporting", "generali_reporting"),
        ("pdqm", "generali_pdqm"),
    ]:
        assert lit(tabbar_window([GENERALI], active)) == [key], key


def test_a_shared_endpoint_claimed_by_two_tenants_is_broken_by_membership():
    """sydoc and ms02 both mount the global workitems page."""
    shared = "workitems_overview"
    nav = [
        tenant("sydoc", [custom("workitems", shared, endpoint=shared)]),
        tenant("ms02", [custom("workitems", shared, endpoint=shared)]),
    ]
    assert tabbar_window(nav, shared, own_tenant="ms02")[0][0]["url"] == "/workitems"
    picked = tabbar_window(nav, shared, own_tenant="ms02")
    assert picked and picked[0][1] is True

    # Nobody's own tenant -- refuse to guess rather than light the wrong one.
    assert tabbar_window(nav, shared, own_tenant=None) == []


def test_no_match_falls_back_to_the_solo_tenant_then_the_remembered_one():
    nav = [GENERALI]
    # Their portal IS the tenant.
    assert keys(tabbar_window(nav, "profile", solo=True)) == [
        "dashboard",
        "documents",
        "reporting",
    ]
    # Staff who picked a tenant keep it.
    assert keys(tabbar_window(nav, "profile", remembered="generali"))[0] == "dashboard"
    # Staff who picked nothing get the Global entries (an empty window).
    assert tabbar_window(nav, "profile") == []


def test_list_pages_match_on_their_generated_active_page():
    nav = [tenant("acme", [listpage("alpha"), listpage("bravo")])]
    assert lit(tabbar_window(nav, "tenant_acme_bravo")) == ["bravo"]


# ----------------------------------------------------------- the window --


def test_active_page_sits_in_the_middle():
    slots = tabbar_window([GENERALI], "generali_additionalservices")  # index 3 of 8
    assert keys(slots) == ["reporting", "additional-services", "base-services"]
    assert slots[1][1] is True, "the active page must be the middle slot"


def test_window_clamps_at_the_first_page():
    slots = tabbar_window([GENERALI], "generali_dashboard")  # index 0
    assert keys(slots) == ["dashboard", "documents", "reporting"]
    assert slots[0][1] is True


def test_window_clamps_at_the_last_page():
    slots = tabbar_window([GENERALI], "generali_importstatus")  # index 7 of 8
    assert keys(slots) == ["project-management", "pdqm", "import-status"]
    assert slots[2][1] is True


def test_no_wrap_at_either_end():
    """The first window never contains the last page, and vice versa."""
    first = keys(tabbar_window([GENERALI], "generali_dashboard"))
    last = keys(tabbar_window([GENERALI], "generali_importstatus"))
    assert "import-status" not in first
    assert "dashboard" not in last


def test_a_short_list_is_not_a_special_case():
    nav = [tenant("acme", [listpage("only")])]
    assert keys(tabbar_window(nav, "tenant_acme_only")) == ["only"]


def test_window_start_is_clamped_arithmetic():
    assert window_start(-1, 8) == 0  # nothing active
    assert window_start(0, 8) == 0
    assert window_start(1, 8) == 0
    assert window_start(4, 8) == 3
    assert window_start(7, 8) == 5
    assert window_start(1, 2) == 0  # shorter than the window


# ------------------------------------------------- the phone tenant switcher --

from nx_lib.tabbar import active_tenant_code, tenant_switcher  # noqa: E402

MS02 = tenant("ms02", [custom("dashboard", "tenant_ms02_dashboard"), listpage("workitems")])
SYDOC = tenant("sydoc", [custom("dashboard", "tenant_sydoc_dashboard"), listpage("workitems")])


def test_switcher_offers_every_tenant_and_marks_the_current_one():
    rows = tenant_switcher([GENERALI, MS02, SYDOC], "generali_pdqm")
    assert [code for code, _, _, _ in rows] == ["generali", "ms02", "sydoc"]
    assert [code for code, _, _, cur in rows if cur] == ["generali"]


def test_switcher_links_the_tenants_first_page_not_a_query_parameter():
    """`?tenant=<code>` only works for routes that call apply_tenant_scope.

    Generali's pages are custom routes and never do, so a switcher built on
    the query parameter would appear to do nothing for the tenant that needed
    it most. Linking a real page is what makes the bar follow.
    """
    rows = tenant_switcher([GENERALI, MS02], "generali_pdqm")
    urls = {code: url for code, _, url, _ in rows}
    assert urls["generali"] == "/dashboard"  # Generali's first page
    assert "?tenant=" not in urls["generali"]


def test_switcher_is_empty_for_a_solo_tenant_user():
    """#255: for a member the tenant IS the portal, so it is never named."""
    assert tenant_switcher([GENERALI], "generali_pdqm", solo=True) == []


def test_switcher_is_empty_with_nothing_to_switch_between():
    assert tenant_switcher([GENERALI], "generali_pdqm") == []
    assert tenant_switcher([], "anything") == []


def test_switcher_skips_a_tenant_with_no_visible_pages():
    """Permission filtering can empty a tenant's page list; a chip linking
    nowhere is worse than no chip."""
    empty = tenant("ghost", [])
    rows = tenant_switcher([GENERALI, MS02, empty], "generali_pdqm")
    assert "ghost" not in [code for code, _, _, _ in rows]


def test_switcher_agrees_with_the_bar_about_the_current_tenant():
    """One rule, two readers -- the chip and the bar cannot disagree."""
    nav = [GENERALI, MS02, SYDOC]
    for active, expected in [
        ("generali_documents", "generali"),
        ("tenant_ms02_dashboard", "ms02"),
        ("profile", None),
    ]:
        assert active_tenant_code(nav, active) == expected, active
        current = [c for c, _, _, cur in tenant_switcher(nav, active) if cur]
        assert current == ([expected] if expected else []), active


# --------------------------------------------- slot view-transition names --

from nx_lib.tabbar import slot_transition_name  # noqa: E402


def test_a_slot_is_named_after_its_page_not_its_position():
    """The whole carousel effect rests on this.

    Same page -> same name in both documents, so the browser morphs it from
    the slot it used to occupy to the one it occupies now. Naming by position
    would pin every slot in place and cross-fade its label into a different
    page's, which reads as a glitch rather than as movement.
    """
    assert slot_transition_name("documents") == "nx-tab-documents"
    assert slot_transition_name("import-status") == "nx-tab-import-status"


def test_transition_names_are_valid_css_idents():
    """A malformed ident silently drops the whole declaration."""
    assert slot_transition_name("Weird Key!") == "nx-tab-weird-key"
    assert slot_transition_name("a/b c") == "nx-tab-a-b-c"
    assert slot_transition_name("--leading") == "nx-tab-leading"


def test_a_missing_key_still_yields_something_usable():
    assert slot_transition_name("") == "nx-tab-slot"
    assert slot_transition_name(None) == "nx-tab-slot"


def test_every_slot_in_a_window_gets_a_distinct_name():
    """Duplicate names inside one document make the transition invalid."""
    for active in ("generali_dashboard", "generali_reporting", "generali_importstatus"):
        names = [slot_transition_name(p["key"]) for p, _ in tabbar_window([GENERALI], active)]
        assert len(names) == len(set(names)), (active, names)


def test_a_page_keeps_its_name_as_the_window_slides_past_it():
    """documents is slot 2 before the swipe and slot 1 after -- same name."""
    before = {
        p["key"]: i for i, (p, _) in enumerate(tabbar_window([GENERALI], "generali_documents"))
    }
    after = {
        p["key"]: i for i, (p, _) in enumerate(tabbar_window([GENERALI], "generali_reporting"))
    }
    assert before["documents"] == 1 and after["documents"] == 0, (before, after)
    assert slot_transition_name("documents") == slot_transition_name("documents")
