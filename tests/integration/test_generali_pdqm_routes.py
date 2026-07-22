"""Integration tests for the Generali PDQM read endpoints' own-records row scope.

Regression for: api_generali_pdqm_list, api_generali_pdqm_organizations and
generali_pdqm_monthreport (nx_lib/views/generali.py) never applied the
`UserID = session["userid"]` restriction that every sibling generali module
(Attendance, BaseServices, ProjectManagement) applies for callers who lack
`generali.pdqm.edit.organizational` / `generali.pdqm.edit.transorganizational`.
A generali.pdqm.view-only caller could see every org's PDQM entries. PDQM's
own edit/delete endpoints already call `_check_generali_record_org` for this
exact purpose (proving the intent), the three read endpoints were missed.

Session permissions are reloaded from the DB on EVERY request by
nx_lib.hooks._reload_user_permissions (a before_request hook), so the
permission set for the logged-in test user must be patched at the source
(nx_lib.hooks.load_permissions_for_user) rather than via session_transaction,
which would just be clobbered on the next request (same seam used by
tests/integration/test_workitems_routes.py).

engine_generali_db / engine_nexora_db are patched with lightweight fakes that
interpret the exact SQL shapes the three endpoints issue (including the
own-records filter under test), so these tests are hermetic against the TEST
env's real Generali DB, which is not guaranteed to exist / carry PDQM rows.
"""

from datetime import date, datetime

import pytest

import nx_lib.hooks as hooks
import nx_lib.views.generali as gv

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeCursorBase:
    def __init__(self):
        self._result = []

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        pass


class _FakePdqmCursor(_FakeCursorBase):
    """Interprets the PDQMReport query shapes issued by api_generali_pdqm_list,
    api_generali_pdqm_organizations and generali_pdqm_monthreport against an
    in-memory row set, including a UserID = ? restriction if present."""

    def __init__(self, rows, log):
        super().__init__()
        self._rows = rows
        self._log = log

    def execute(self, sql, params=None):
        params = list(params or [])
        normalized = " ".join(sql.split())
        self._log.append((normalized, params))
        restrict = "UserID = ?" in normalized
        rows = self._rows

        if "GROUP BY ParentCategory" in normalized:
            # generali_pdqm_monthreport: params = [first_day, last_day, (userid)]
            first_day, last_day = str(params[0]), str(params[1])
            rows = [r for r in rows if first_day <= str(r["ForDate"]) <= last_day]
            if restrict:
                rows = [r for r in rows if r["UserID"] == params[2]]
            groups = {}
            for r in rows:
                groups.setdefault(r["ParentCategory"], []).append(r)
            self._result = [
                (cat, len(items), sum(i["Quantity"] for i in items))
                for cat, items in sorted(groups.items())
            ]
        elif "SELECT DISTINCT UserID FROM" in normalized:
            # api_generali_pdqm_organizations
            if restrict:
                rows = [r for r in rows if r["UserID"] == params[-1]]
            seen = []
            for r in rows:
                if r["UserID"] not in seen:
                    seen.append(r["UserID"])
            self._result = [(u,) for u in seen]
        elif "COUNT(*), SUM(Quantity)" in normalized:
            # api_generali_pdqm_list aggregate
            if restrict:
                rows = [r for r in rows if r["UserID"] == params[0]]
            self._result = [(len(rows), sum(r["Quantity"] for r in rows) if rows else None)]
        elif "SELECT ID, Quantity, UserID, ForDate" in normalized:
            # api_generali_pdqm_list page query
            if restrict:
                rows = [r for r in rows if r["UserID"] == params[0]]
            self._result = [
                (
                    r["ID"],
                    r["Quantity"],
                    r["UserID"],
                    r["ForDate"],
                    r["ParentCategory"],
                    r["ParentSubCategory"],
                    r["SubCategory"],
                    r["RecordDateTime"],
                )
                for r in rows
            ]
        else:
            self._result = []


class _FakeUsersCursor(_FakeCursorBase):
    """Interprets the Users-table lookups used to enrich PDQM rows/orgs
    (_generali_orgs_for_userids + the list endpoint's fullname/orgCode join)."""

    def __init__(self, users, log):
        super().__init__()
        self._users = users
        self._log = log

    def execute(self, sql, params=None):
        params = list(params or [])
        normalized = " ".join(sql.split())
        self._log.append((normalized, params))
        if "organizationcode, o.organization" in normalized:
            seen = set()
            out = []
            for uid in params:
                u = self._users.get(uid)
                if u and u["orgcode"] not in seen:
                    seen.add(u["orgcode"])
                    out.append((u["orgcode"], u["orgname"]))
            self._result = out
        elif "SELECT userid, fullname, organizationcode FROM Users WHERE userid IN" in normalized:
            self._result = [
                (uid, self._users[uid]["fullname"], self._users[uid]["orgcode"])
                for uid in params
                if uid in self._users
            ]
        else:
            self._result = []


class _FakeConn:
    def __init__(self, cursor_factory):
        self._cursor_factory = cursor_factory

    def cursor(self):
        return self._cursor_factory()

    def close(self):
        pass


class _FakeEngine:
    def __init__(self, cursor_factory):
        self._cursor_factory = cursor_factory

    def raw_connection(self):
        return _FakeConn(self._cursor_factory)


SELF_QTY = 777
OTHER_QTY = 888
SELF_CATEGORY = "ZzzCatSelfOnly"
OTHER_CATEGORY = "ZzzCatOtherOnly"


def _seed_rows(self_uid, other_uid):
    return [
        {
            "ID": 1,
            "Quantity": SELF_QTY,
            "UserID": self_uid,
            "ForDate": date(2026, 7, 5),
            "ParentCategory": SELF_CATEGORY,
            "ParentSubCategory": None,
            "SubCategory": "Sub1",
            "RecordDateTime": datetime(2026, 7, 5, 10, 0, 0),
        },
        {
            "ID": 2,
            "Quantity": OTHER_QTY,
            "UserID": other_uid,
            "ForDate": date(2026, 7, 6),
            "ParentCategory": OTHER_CATEGORY,
            "ParentSubCategory": None,
            "SubCategory": "Sub2",
            "RecordDateTime": datetime(2026, 7, 6, 10, 0, 0),
        },
    ]


def _wire_fake_db(monkeypatch, self_uid, other_uid):
    rows = _seed_rows(self_uid, other_uid)
    users = {
        self_uid: {"fullname": "Self User", "orgcode": "ORGSELF", "orgname": "Org Self"},
        other_uid: {"fullname": "Other User", "orgcode": "ORGOTHER", "orgname": "Org Other"},
    }
    pdqm_log = []
    monkeypatch.setattr(
        gv, "engine_generali_db", _FakeEngine(lambda: _FakePdqmCursor(rows, pdqm_log))
    )
    monkeypatch.setattr(gv, "engine_nexora_db", _FakeEngine(lambda: _FakeUsersCursor(users, [])))
    return pdqm_log


def _grant_perms(monkeypatch, perms):
    monkeypatch.setattr(hooks, "load_permissions_for_user", lambda uid: list(perms))


@pytest.fixture()
def pdqm_uids(user_client):
    """(self_uid, other_uid) -- self_uid is the real seeded userid behind
    user_client (session["userid"], type as set by the login flow -- not
    assumed to be int); other_uid is a distinct id whose PDQM rows must never
    leak into a view-only caller's results."""
    with user_client.session_transaction() as sess:
        self_uid = sess["userid"]
    return self_uid, f"other-{self_uid}"


# ============================ /api/generali/pdqm (list) ======================


def test_pdqm_list_view_only_scoped_to_own_records(user_client, pdqm_uids, monkeypatch):
    self_uid, other_uid = pdqm_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.pdqm.view"])

    resp = user_client.get("/api/generali/pdqm")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    user_ids_seen = {r["userId"] for r in body["records"]}
    assert user_ids_seen == {self_uid}
    assert other_uid not in user_ids_seen
    assert body["totalQuantity"] == SELF_QTY
    assert body["pagination"]["total_records"] == 1


def test_pdqm_list_org_edit_perm_sees_all(user_client, pdqm_uids, monkeypatch):
    """Regression: a caller WITH generali.pdqm.edit.organizational must still
    see every org's rows -- the restrict must not fire for callers entitled
    to edit."""
    self_uid, other_uid = pdqm_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.pdqm.view", "generali.pdqm.edit.organizational"])

    resp = user_client.get("/api/generali/pdqm")
    assert resp.status_code == 200
    body = resp.get_json()
    user_ids_seen = {r["userId"] for r in body["records"]}
    assert user_ids_seen == {self_uid, other_uid}
    assert body["totalQuantity"] == SELF_QTY + OTHER_QTY


# ============================ /api/generali/pdqm/organizations ===============


def test_pdqm_organizations_view_only_scoped_to_own_org(user_client, pdqm_uids, monkeypatch):
    self_uid, other_uid = pdqm_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.pdqm.view"])

    resp = user_client.get("/api/generali/pdqm/organizations")
    assert resp.status_code == 200
    body = resp.get_json()
    codes = {o["code"] for o in body["organizations"]}
    assert codes == {"ORGSELF"}
    assert "ORGOTHER" not in codes


def test_pdqm_organizations_transorg_perm_sees_all(user_client, pdqm_uids, monkeypatch):
    self_uid, other_uid = pdqm_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.pdqm.view", "generali.pdqm.edit.transorganizational"])

    resp = user_client.get("/api/generali/pdqm/organizations")
    assert resp.status_code == 200
    body = resp.get_json()
    codes = {o["code"] for o in body["organizations"]}
    assert codes == {"ORGSELF", "ORGOTHER"}


# ============================ /generali/pdqm/monthreport ======================


def test_pdqm_monthreport_view_only_scoped_to_own_records(user_client, pdqm_uids, monkeypatch):
    self_uid, other_uid = pdqm_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.pdqm.view"])

    resp = user_client.get("/generali/pdqm/monthreport?year=2026&month=7")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert SELF_CATEGORY in html
    assert OTHER_CATEGORY not in html
    assert str(SELF_QTY) in html


def test_pdqm_monthreport_transorg_perm_sees_all(user_client, pdqm_uids, monkeypatch):
    self_uid, other_uid = pdqm_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.pdqm.view", "generali.pdqm.edit.transorganizational"])

    resp = user_client.get("/generali/pdqm/monthreport?year=2026&month=7")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert SELF_CATEGORY in html
    assert OTHER_CATEGORY in html
