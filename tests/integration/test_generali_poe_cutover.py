r"""The Base Services page flips POE by itself on 2026-10-01.

Companion to `tests/unit/test_generali_base_categories.py`, which pins the
date logic and the template's gating. This renders the **real page through the
real route** and reads the two category arrays out of the HTML the browser
would actually receive, because the gating is Jinja and a unit test on the
template source cannot prove the branch renders the way it reads.

Why a date and not a deploy: "release this on the 30th" is a thing somebody
has to remember, and both kinds of mistake cost real work — ship early and
nobody can book their September hours, ship late and nobody can book their
October ones. Pinning the date lets the release go out whenever it suits.
"""

import re
from datetime import date

import nx_lib.hooks as hooks
import nx_lib.views.generali.baseservices as bs


def _grant_view(monkeypatch):
    monkeypatch.setattr(
        hooks, "load_permissions_for_user", lambda uid: ["tenant.generali.baseservices.view"]
    )


def _arrays(html):
    """(bookable, filter-only) as the browser receives them."""

    def pull(name):
        m = re.search(rf"const\s+{name}\s*=\s*\[(.*?)\]\s*;", html, re.S)
        assert m, f"{name} missing from the rendered page"
        return re.findall(r'"([^"]+)"', m.group(1))

    return pull("BASE_CATEGORIES"), pull("LEGACY_CATEGORIES")


def _render(client, monkeypatch, today):
    _grant_view(monkeypatch)
    monkeypatch.setattr(bs, "poe_has_moved", lambda *a, **k: today >= bs.POE_CUTOVER)
    resp = client.get("/generali/baseServices")
    assert resp.status_code == 200, resp.status_code
    return _arrays(resp.data.decode())


def test_before_the_cutover_poe_is_bookable(user_client, monkeypatch):
    bookable, filter_only = _render(user_client, monkeypatch, date(2026, 9, 30))
    assert "POE" in bookable, "POE must stay bookable through September"
    assert "POE" not in filter_only, "POE would render twice in the filter dropdown"


def test_on_the_cutover_poe_becomes_filter_only(user_client, monkeypatch):
    bookable, filter_only = _render(user_client, monkeypatch, date(2026, 10, 1))
    assert "POE" not in bookable, "POE is booked under Zusatzleistungen from 1 October"
    assert "POE" in filter_only, (
        "POE vanished from the filter as well -- every hour booked before the "
        "move is still in BaseServiceEntries and still counts in the month "
        "report, but nothing in the UI could select those rows"
    )


def test_the_other_categories_are_untouched_either_side(user_client, monkeypatch):
    before, _ = _render(user_client, monkeypatch, date(2026, 9, 30))
    after, _ = _render(user_client, monkeypatch, date(2026, 10, 1))
    unchanged = ["Physical Mailroom, AVOR & Scanning", "Nk1 & NK2", "PPR"]
    assert [c for c in before if c != "POE"] == unchanged
    assert after == unchanged


def test_the_legacy_combined_category_survives_both_sides(user_client, monkeypatch):
    """ "POE / PPR" predates this move and is not part of it."""
    for today in (date(2026, 9, 30), date(2026, 10, 1)):
        _, filter_only = _render(user_client, monkeypatch, today)
        assert "POE / PPR" in filter_only, today
