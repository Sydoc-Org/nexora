"""The phone quick entry on the four Generali booking pages (#354).

Base Services, Additional Services, Project Management and PDQM each open with
a "book hours" / "enter quantities" board on a touch phone. These tests drive
it the way a person would -- day, category path, amount, Save, Undo -- and
assert the request the board sends, so a refactor of the shared component
(static/js/generali_quick_entry.js) cannot quietly change what gets booked.

Two things the TEST environment does not have, and how this file gets them:

* **No Generali database.** The pages render without one (only their APIs
  touch it), so every /api/generali/<table>... call is answered by
  ``page.route`` with a small in-memory fake, which also records the POSTs.
* **No Generali add permissions.** sql/test/seed.sql seeds only
  tenant.generali.baseservices.view, on purpose (see its comment). The
  ``generali_booker`` fixture grants the view/add codes to admin@test.local
  through dbo.UserPermissionOverride for this module only and removes them
  afterwards. The server caches permissions for up to 30s, and any non-GET to
  /admin clears that cache (hooks._invalidate_user_cache) -- so the fixture
  sends one, rather than sleeping out the TTL.
"""

import json
from datetime import date

import pytest
from playwright.sync_api import expect
from sqlalchemy import bindparam, text

from tests.e2e.test_mobile_nav import PHONE, _login, _tune

ADMIN = "admin@test.local"
TABLES = ("baseservices", "attendance", "projectmanagement", "pdqm")
CODES = [f"tenant.generali.{t}.{a}" for t in TABLES for a in ("view", "add")]

REASONS = ["bereits korrigierte", "nicht auffindbar", "Recherche", "Verstorben", "Wegzug Ausland"]
CATEGORIES = {
    "attendance": {
        "Material- & Warenlogistik": ["Materialbestellung", "Kopierpapier auffüllen"],
        "POE": [],
    },
    "pdqm": {
        "Adressverifikation": {"": ["QSTAT 4", "QSTAT 26"]},
        "Dubletten": {"": []},
        "GAV Retouren": {"aus sonstigen Quellen": REASONS},
    },
}


@pytest.fixture(scope="module")
def generali_booker(nexora_server):
    """Grant admin@test.local view+add on the four tables, for this module only."""
    from nx_lib.db import engine_nexora_db

    with engine_nexora_db.begin() as conn:
        for code in CODES:
            conn.execute(
                text(
                    "IF NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = :c) "
                    "INSERT INTO dbo.Permission (Code, Description) VALUES (:c, :c)"
                ),
                {"c": code},
            )
        conn.execute(
            text(
                "INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect) "
                "SELECT u.userID, p.PermissionID, 'A' FROM dbo.Users u, dbo.Permission p "
                "WHERE u.username = :u AND p.Code IN :codes AND NOT EXISTS ("
                "  SELECT 1 FROM dbo.UserPermissionOverride o"
                "  WHERE o.UserID = u.userID AND o.PermissionID = p.PermissionID)"
            ).bindparams(bindparam("codes", expanding=True)),
            {"u": ADMIN, "codes": list(CODES)},
        )
    yield
    with engine_nexora_db.begin() as conn:
        conn.execute(
            text(
                "DELETE o FROM dbo.UserPermissionOverride o "
                "JOIN dbo.Users u ON u.userID = o.UserID "
                "JOIN dbo.Permission p ON p.PermissionID = o.PermissionID "
                "WHERE u.username = :u AND p.Code IN :codes AND o.Effect = 'A'"
            ).bindparams(bindparam("codes", expanding=True)),
            {"u": ADMIN, "codes": list(CODES)},
        )


@pytest.fixture()
def touch_page(browser):
    """A touch phone, as test_mobile_nav.phone_page: the quick entry is gated on
    `pointer: coarse`, which only a has_touch/is_mobile context reports."""
    if browser.browser_type.name == "firefox":
        pytest.skip("is_mobile is unsupported on Firefox")
    context = browser.new_context(viewport=PHONE, has_touch=True, is_mobile=True)
    yield _tune(context.new_page())
    context.close()


@pytest.fixture()
def mouse_page(browser):
    """The same width with a mouse (`pointer: fine`): a narrow desktop window."""
    context = browser.new_context(viewport=PHONE)
    yield _tune(context.new_page())
    context.close()


def _clear_permission_cache(page, base):
    # A non-GET under /admin clears the server's per-user cache; the response
    # itself (CSRF refusal, 404, ...) does not matter.
    page.request.post(f"{base}/admin/__e2e_clear_user_cache")


class FakeGenerali:
    """In-memory stand-in for one table's /api/generali/<table> family."""

    def __init__(self, table):
        self.table = table
        self.rows = []
        self.posts = []
        self.undos = []
        self.next_id = 100

    def handle(self, route):
        req = route.request
        url = req.url.split("?")[0]
        if req.method == "POST" and url.endswith("/undo"):
            rid = int(url.rstrip("/").split("/")[-2])
            self.undos.append(rid)
            self.rows = [r for r in self.rows if r["id"] != rid]
            return route.fulfill(json={"success": True})
        if req.method == "POST":
            body = json.loads(req.post_data or "{}")
            self.posts.append(body)
            self.next_id += 1
            self.rows.insert(0, {"id": self.next_id, **body})
            return route.fulfill(json={"success": True, "id": self.next_id})
        if url.endswith("/categories"):
            return route.fulfill(
                json={"success": True, "categories": CATEGORIES[self.table], "translations": {}}
            )
        if url.endswith(("/orgUsers", "/filterUsers")):
            return route.fulfill(json={"success": True, "users": []})
        if url.endswith("/organizations"):
            return route.fulfill(json={"success": True, "organizations": []})
        # the list endpoint
        return route.fulfill(
            json={
                "success": True,
                "records": self.rows,
                "pagination": {
                    "page": 1,
                    "per_page": 25,
                    "total_records": len(self.rows),
                    "total_pages": 1,
                },
                "totalHours": sum(r.get("effortInHours") or 0 for r in self.rows),
                "totalQuantity": sum(r.get("quantity") or 0 for r in self.rows),
            }
        )


PAGES = {
    "baseservices": "/generali/baseServices",
    "attendance": "/generali/additionalServices",
    "projectmanagement": "/generali/projectManagement",
    "pdqm": "/generali/pdqm",
}


def _open(page, base, table):
    fake = FakeGenerali(table)
    page.route(f"**/api/generali/{table}**", fake.handle)
    _login(page, base, ADMIN)
    _clear_permission_cache(page, base)
    page.goto(f"{base}{PAGES[table]}")
    expect(page.locator("#gqQuick")).to_be_visible()
    return fake


def _tap(page, selector, text):
    page.locator(selector, has_text=text).first.click()


# What to tap on each page, and the body that must come out of it.
FLOWS = {
    "baseservices": (
        [(".gq-cat", "PPR")],
        "2",
        {"category": "PPR", "effortInHours": 2},
        "PPR",
    ),
    "attendance": (
        [(".gq-cat", "Material- & Warenlogistik"), (".gq-sub", "Materialbestellung")],
        "1",
        {
            "parentCategory": "Material- & Warenlogistik",
            "subCategory": "Materialbestellung",
            "effortInHours": 1,
        },
        "Materialbestellung",
    ),
    "projectmanagement": (
        [],
        "4",
        {"category": "Project Effort", "effortInHours": 4, "comment": "Rollout"},
        "Rollout",
    ),
    "pdqm": (
        [
            (".gq-cat", "GAV Retouren"),
            (".gq-sub", "aus sonstigen Quellen"),
            (".gq-sub", "Verstorben"),
        ],
        "5",
        {
            "parentCategory": "GAV Retouren",
            "parentSubCategory": "aus sonstigen Quellen",
            "subCategory": "Verstorben",
            "quantity": 5,
        },
        "Verstorben",
    ),
}


@pytest.mark.parametrize("table", TABLES)
def test_quick_entry_books_and_undoes(nexora_server, touch_page, generali_booker, table):
    page = touch_page
    fake = _open(page, nexora_server, table)
    taps, amount, expected, pill_word = FLOWS[table]

    save = page.locator("#gqQuickSave")
    expect(save).to_be_disabled()
    for selector, label in taps:
        _tap(page, selector, label)
    if table == "projectmanagement":
        page.fill("#gqQuickComment", "Rollout")
    page.locator(f'#gqQuickPresets [data-amount="{amount}"]').click()
    expect(save).to_be_enabled()
    save.click()

    pill = page.locator("#gqUndo")
    expect(pill).to_be_visible()
    expect(pill.locator(".nx-undo__text")).to_contain_text(pill_word)
    assert fake.posts == [{"forDate": date.today().isoformat(), **expected}]

    pill.locator(".nx-undo__btn").click()
    expect(pill).to_be_hidden(timeout=6000)  # "Undone" shows, then the pill fades
    assert fake.undos == [101]
    assert fake.rows == []


def test_quick_entry_needs_the_last_category_level(nexora_server, touch_page, generali_booker):
    """PDQM's GAV Retouren is three levels deep: picking the parent, or the
    parent and the source, is not a complete category and must not save."""
    page = touch_page
    _open(page, nexora_server, "pdqm")
    page.locator('#gqQuickPresets [data-amount="1"]').click()
    save = page.locator("#gqQuickSave")
    _tap(page, ".gq-cat", "GAV Retouren")
    expect(save).to_be_disabled()
    _tap(page, ".gq-sub", "aus sonstigen Quellen")
    expect(save).to_be_disabled()
    _tap(page, ".gq-sub", "Wegzug Ausland")
    expect(save).to_be_enabled()
    # Dubletten has no lower level at all: saveable straight away
    _tap(page, ".gq-cat", "Dubletten")
    expect(save).to_be_enabled()


def test_quick_entry_never_shows_on_a_narrow_desktop(nexora_server, mouse_page, generali_booker):
    page = mouse_page
    page.route("**/api/generali/baseservices**", FakeGenerali("baseservices").handle)
    _login(page, nexora_server, ADMIN)
    _clear_permission_cache(page, nexora_server)
    page.goto(f"{nexora_server}/generali/baseServices")
    expect(page.locator('[data-testid="generali-base-services-add-entry"]')).to_be_visible()
    expect(page.locator("#gqQuick")).to_be_hidden()
