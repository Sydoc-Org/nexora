"""Integration test for the Generali Reporting list endpoint's own-records row scope.

Regression for: api_generali_reporting_list (nx_lib/views/generali.py) built its
WHERE clause only from request filters, never applying a
`ReportByUserID = session["userid"]` restriction for callers who lack
`generali.reporting.edit.organizational` / `generali.reporting.edit.transorganizational`
-- unlike every sibling generali module (Attendance, BaseServices,
ProjectManagement, PDQM, see tests/integration/test_generali_pdqm_routes.py).
A generali.reporting.view-only caller could see every org's reporting rows.

Session permissions are reloaded from the DB on EVERY request by
nx_lib.hooks._reload_user_permissions (a before_request hook), so the
permission set for the logged-in test user must be patched at the source
(nx_lib.hooks.load_permissions_for_user) rather than via session_transaction,
which would just be clobbered on the next request (same seam used by
tests/integration/test_generali_pdqm_routes.py).

engine_generali_db / engine_nexora_db are patched with lightweight fakes that
interpret the exact SQL shapes api_generali_reporting_list issues (including
the own-records filter under test), so this test is hermetic against the TEST
env's real Generali DB.
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


class _FakeReportingCursor(_FakeCursorBase):
    """Interprets the reportingiss query shapes issued by
    api_generali_reporting_list against an in-memory row set, including a
    ReportByUserID = ? restriction if present."""

    def __init__(self, rows, log):
        super().__init__()
        self._rows = rows
        self._log = log

    def execute(self, sql, params=None):
        params = list(params or [])
        normalized = " ".join(sql.split())
        self._log.append((normalized, params))
        restrict = "ReportByUserID = ?" in normalized
        rows = self._rows
        if restrict:
            rows = [r for r in rows if r["ReportByUserID"] == params[0]]

        if "SELECT COUNT(*) FROM" in normalized:
            self._result = [(len(rows),)]
        elif "SELECT ID, ReportForDate" in normalized:
            self._result = [
                (
                    r["ID"],
                    r["ReportForDate"],
                    r["ReportTimeStamp"],
                    r["ReportByUserID"],
                    r["ontime"],
                    r["category"],
                )
                for r in rows
            ]
        else:
            self._result = []


class _FakeUsersCursor(_FakeCursorBase):
    """Interprets the Users-table lookup used to enrich reporting rows with
    fullname/orgCode."""

    def __init__(self, users, log):
        super().__init__()
        self._users = users
        self._log = log

    def execute(self, sql, params=None):
        params = list(params or [])
        normalized = " ".join(sql.split())
        self._log.append((normalized, params))
        if "SELECT userid, fullname, organizationcode FROM Users WHERE userid IN" in normalized:
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


SELF_CATEGORY = "export_post"
OTHER_CATEGORY = "delivery_regular"


def _seed_rows(self_uid, other_uid):
    return [
        {
            "ID": 1,
            "ReportForDate": date(2026, 7, 5),
            "ReportTimeStamp": datetime(2026, 7, 5, 10, 0, 0),
            "ReportByUserID": self_uid,
            "ontime": 1,
            "category": SELF_CATEGORY,
        },
        {
            "ID": 2,
            "ReportForDate": date(2026, 7, 6),
            "ReportTimeStamp": datetime(2026, 7, 6, 10, 0, 0),
            "ReportByUserID": other_uid,
            "ontime": 0,
            "category": OTHER_CATEGORY,
        },
    ]


def _wire_fake_db(monkeypatch, self_uid, other_uid):
    rows = _seed_rows(self_uid, other_uid)
    users = {
        self_uid: {"fullname": "Self User", "orgcode": "ORGSELF"},
        other_uid: {"fullname": "Other User", "orgcode": "ORGOTHER"},
    }
    reporting_log = []
    monkeypatch.setattr(
        gv, "engine_generali_db", _FakeEngine(lambda: _FakeReportingCursor(rows, reporting_log))
    )
    monkeypatch.setattr(gv, "engine_nexora_db", _FakeEngine(lambda: _FakeUsersCursor(users, [])))
    return reporting_log


def _grant_perms(monkeypatch, perms):
    monkeypatch.setattr(hooks, "load_permissions_for_user", lambda uid: list(perms))


@pytest.fixture()
def reporting_uids(user_client):
    """(self_uid, other_uid) -- self_uid is the real seeded userid behind
    user_client (session["userid"]); other_uid is a distinct id whose
    reporting rows must never leak into a view-only caller's results."""
    with user_client.session_transaction() as sess:
        self_uid = sess["userid"]
    return self_uid, f"other-{self_uid}"


# ============================ /api/generali/reporting =======================


def test_reporting_list_view_only_scoped_to_own_records(user_client, reporting_uids, monkeypatch):
    self_uid, other_uid = reporting_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.reporting.view"])

    resp = user_client.get("/api/generali/reporting")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    user_ids_seen = {r["reportByUserID"] for r in body["records"]}
    assert user_ids_seen == {self_uid}
    assert other_uid not in user_ids_seen
    assert body["pagination"]["total_records"] == 1


def test_reporting_list_org_edit_perm_sees_all(user_client, reporting_uids, monkeypatch):
    """Regression: a caller WITH generali.reporting.edit.organizational must
    still see every org's rows -- the restrict must not fire for callers
    entitled to edit."""
    self_uid, other_uid = reporting_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(monkeypatch, ["generali.reporting.view", "generali.reporting.edit.organizational"])

    resp = user_client.get("/api/generali/reporting")
    assert resp.status_code == 200
    body = resp.get_json()
    user_ids_seen = {r["reportByUserID"] for r in body["records"]}
    assert user_ids_seen == {self_uid, other_uid}
    assert body["pagination"]["total_records"] == 2


def test_reporting_list_transorg_edit_perm_sees_all(user_client, reporting_uids, monkeypatch):
    """Same guarantee for the transorganizational edit perm."""
    self_uid, other_uid = reporting_uids
    _wire_fake_db(monkeypatch, self_uid, other_uid)
    _grant_perms(
        monkeypatch, ["generali.reporting.view", "generali.reporting.edit.transorganizational"]
    )

    resp = user_client.get("/api/generali/reporting")
    assert resp.status_code == 200
    body = resp.get_json()
    user_ids_seen = {r["reportByUserID"] for r in body["records"]}
    assert user_ids_seen == {self_uid, other_uid}
    assert body["pagination"]["total_records"] == 2
