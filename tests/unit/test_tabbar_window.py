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
