"""The phone quick-report's "Undo": POST /api/generali/reporting/<id>/undo.

It is "I tapped the wrong button", not a delete right: only the caller's OWN
report, only within UNDO_WINDOW_SECONDS of making it, and only with
reporting.add. ISS users hold add but no delete permission; this must not
become a back door to deleting anyone else's report.

Same seams as test_generali_reporting_routes.py: permissions patched at
hooks.load_permissions_for_user, the Generali engine replaced by a fake that
interprets the endpoint's two SQL shapes.
"""

import pytest

import nx_lib.hooks as hooks
import nx_lib.views.generali as gv
from nx_lib.views.generali.reporting import UNDO_WINDOW_SECONDS


class _FakeCursor:
    def __init__(self, rows, log):
        self._rows, self._log, self._result = rows, log, []

    def execute(self, sql, params=None):
        params = list(params or [])
        normalized = " ".join(sql.split())
        self._log.append((normalized, params))
        if normalized.startswith("SELECT ReportByUserID, DATEDIFF"):
            r = self._rows.get(params[0])
            self._result = [(r["owner"], r["age"])] if r else []
        elif normalized.startswith("DELETE FROM [dbo].[IssReports]"):
            rid, uid = params
            if rid in self._rows and str(self._rows[rid]["owner"]) == str(uid):
                del self._rows[rid]
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def commit(self):
        pass

    def close(self):
        pass


class _FakeEngine:
    def __init__(self, rows, log):
        self._rows, self._log = rows, log

    def raw_connection(self):
        return _FakeConn(_FakeCursor(self._rows, self._log))


@pytest.fixture()
def wired(user_client, monkeypatch):
    with user_client.session_transaction() as sess:
        me = sess["userid"]
    rows = {
        1: {"owner": me, "age": 30},  # mine, fresh
        2: {"owner": f"other-{me}", "age": 30},  # someone else's
        3: {"owner": me, "age": UNDO_WINDOW_SECONDS + 1},  # mine, too old
    }
    log = []
    monkeypatch.setattr(gv, "engine_generali_db", _FakeEngine(rows, log))
    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: ["tenant.generali.reporting.view", "tenant.generali.reporting.add"],
    )
    return rows, log


def test_undo_deletes_my_fresh_report(user_client, wired):
    rows, log = wired
    resp = user_client.post("/api/generali/reporting/1/undo")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    assert 1 not in rows
    # the DELETE itself is scoped to the caller too, not just the check before it
    assert any(sql.startswith("DELETE") and "ReportByUserID = ?" in sql for sql, _ in log)


def test_undo_refuses_someone_elses_report(user_client, wired):
    rows, _ = wired
    resp = user_client.post("/api/generali/reporting/2/undo")
    assert resp.status_code == 403
    assert 2 in rows


def test_undo_refuses_after_the_window(user_client, wired):
    rows, _ = wired
    resp = user_client.post("/api/generali/reporting/3/undo")
    assert resp.status_code == 409
    assert 3 in rows


def test_undo_needs_the_add_permission(user_client, wired, monkeypatch):
    rows, _ = wired
    monkeypatch.setattr(
        hooks, "load_permissions_for_user", lambda uid: ["tenant.generali.reporting.view"]
    )
    resp = user_client.post("/api/generali/reporting/1/undo")
    assert resp.status_code in (302, 403)
    assert 1 in rows
