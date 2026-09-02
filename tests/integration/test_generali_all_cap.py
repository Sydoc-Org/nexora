"""Integration tests for the ?all=true export cap on the generated Generali
list endpoints (beautify phase-2c Task 5 / D4).

nx_lib/views/generali/_crud.py::_make_list is the single shared factory that
implements ``api_list`` for every Generali table with a ``list_spec``
(Attendance, BaseServices, ProjectManagement, PDQMReport, reportingiss) --
five endpoints, not the three the task brief estimated; fixing the cap here
covers all of them at once. This module exercises it through
api_generali_baseservices_list, which is representative (a plain
``list_spec`` with an aggregate column, no hand-written overrides).

A real 100k+-row Generali table is not available to the test suite, so both
sides of the cap are exercised against a mocked row count / synthetic row
generator (never materializing more than a handful of real dicts) rather than
a genuine multi-million-row dataset. The cap logic under test (comparing
``total_records`` -- itself just an integer from a ``COUNT(*)`` -- against
``ALL_EXPORT_CAP`` and choosing the SQL/params accordingly) does not depend on
the rows actually being real, so this is a faithful test of the code path
without needing a live oversized table.

Session permissions are reloaded from the DB on EVERY request by
nx_lib.hooks._reload_user_permissions (a before_request hook); granting
generali.baseservices.edit.transorganizational alongside .view keeps
_generali_scope_where's SCOPE clause a no-op (no org filter requested), so the
WHERE clause under test stays empty and the synthetic total_records/row count
are exactly what the fake cursor is told to report.
"""

from datetime import date, datetime

import nx_lib.hooks as hooks
import nx_lib.views.generali as gv
from nx_lib.views.generali._crud import ALL_EXPORT_CAP


def _grant_perms(monkeypatch, perms):
    monkeypatch.setattr(hooks, "load_permissions_for_user", lambda uid: list(perms))


class _FakeCapCursor:
    """Interprets the two query shapes _make_list issues for BaseServices:
    the COUNT(*)+SUM aggregate, then the paginated/all SELECT. Row tuples are
    generated on the fly (never pre-materializing ALL_EXPORT_CAP dicts) with a
    single shared UserID so _lookup_users' IN(...) stays a one-element query.
    """

    FAKE_USER_ID = 4242

    def __init__(self, total_records, log):
        self._total_records = total_records
        self._log = log
        self._result = []

    def execute(self, sql, params=None):
        params = list(params or [])
        normalized = " ".join(sql.split())
        self._log.append((normalized, params))

        if normalized.startswith("SELECT COUNT(*)"):
            self._result = [(self._total_records, float(self._total_records))]
        elif normalized.startswith("SELECT ID, EffortInHours"):
            if "OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY" in normalized:
                n = min(self._total_records, params[-1])
            elif "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" in normalized:
                offset, per_page = params[-2], params[-1]
                n = max(0, min(per_page, self._total_records - offset))
            else:  # no pagination clause at all -- true "fetch everything"
                n = self._total_records
            self._result = [
                (i, 1.0, self.FAKE_USER_ID, date(2026, 1, 1), "POE", datetime(2026, 1, 1, 8, 0, 0))
                for i in range(n)
            ]
        else:
            self._result = []

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        pass


class _EmptyUsersCursor:
    """_lookup_users degrades gracefully to unnamed rows on empty results."""

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class _FakeEngine:
    def __init__(self, cursor_factory):
        self._cursor_factory = cursor_factory

    def raw_connection(self):
        return _FakeConn(self._cursor_factory())


def _wire(monkeypatch, total_records):
    log = []
    monkeypatch.setattr(
        gv, "engine_generali_db", _FakeEngine(lambda: _FakeCapCursor(total_records, log))
    )
    monkeypatch.setattr(gv, "engine_nexora_db", _FakeEngine(_EmptyUsersCursor))
    return log


def _grant_baseservices_view_transorg(monkeypatch):
    _grant_perms(
        monkeypatch,
        ["generali.baseservices.view", "generali.baseservices.edit.transorganizational"],
    )


def test_all_true_below_cap_is_unaffected(user_client, monkeypatch):
    """total_records <= the cap: ?all=true returns every matching row, exactly
    as before the cap was added (no FETCH NEXT clause at all)."""
    _grant_baseservices_view_transorg(monkeypatch)
    log = _wire(monkeypatch, total_records=500)

    resp = user_client.get("/api/generali/baseservices?all=true")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert len(body["records"]) == 500
    assert body["pagination"]["total_records"] == 500

    select_calls = [c for c in log if c[0].startswith("SELECT ID, EffortInHours")]
    assert len(select_calls) == 1
    normalized_sql, params = select_calls[0]
    assert "OFFSET" not in normalized_sql
    assert "FETCH NEXT" not in normalized_sql


def test_all_true_above_cap_is_capped_at_exactly_100k(user_client, monkeypatch):
    """total_records > the cap: ?all=true is capped at exactly ALL_EXPORT_CAP
    rows instead of returning every one of the (synthetic) 150,000 matches."""
    _grant_baseservices_view_transorg(monkeypatch)
    log = _wire(monkeypatch, total_records=150_000)

    resp = user_client.get("/api/generali/baseservices?all=true")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert len(body["records"]) == ALL_EXPORT_CAP
    assert ALL_EXPORT_CAP == 100_000
    # total_records still reports the true count -- pagination metadata isn't
    # lied about, only the row payload is capped.
    assert body["pagination"]["total_records"] == 150_000

    select_calls = [c for c in log if c[0].startswith("SELECT ID, EffortInHours")]
    assert len(select_calls) == 1
    normalized_sql, params = select_calls[0]
    assert "OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY" in normalized_sql
    assert params[-1] == ALL_EXPORT_CAP


def test_all_true_exactly_at_cap_is_unaffected(user_client, monkeypatch):
    """Boundary: total_records == the cap must behave like "below" (no
    truncation, no FETCH NEXT clause) -- only a strictly-greater count caps."""
    _grant_baseservices_view_transorg(monkeypatch)
    log = _wire(monkeypatch, total_records=ALL_EXPORT_CAP)

    resp = user_client.get("/api/generali/baseservices?all=true")

    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["records"]) == ALL_EXPORT_CAP

    select_calls = [c for c in log if c[0].startswith("SELECT ID, EffortInHours")]
    normalized_sql, _params = select_calls[0]
    assert "FETCH NEXT" not in normalized_sql


def test_normal_pagination_unaffected_by_cap(user_client, monkeypatch):
    """A plain (non-?all=true) paginated request is untouched by the cap."""
    _grant_baseservices_view_transorg(monkeypatch)
    _wire(monkeypatch, total_records=150_000)

    resp = user_client.get("/api/generali/baseservices?page=1")

    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["records"]) == 20  # per_page, unrelated to the cap
    assert body["pagination"]["total_records"] == 150_000
