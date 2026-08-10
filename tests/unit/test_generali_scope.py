"""Grant-derived org/self scope for the Generali list endpoints
(security audit #193, finding 3).

The list routes (reporting/attendance/baseservices/projectmanagement/pdqm)
used to trust a client-supplied ?organizationcode and only self-restrict when
the caller held NEITHER edit grant -- so a caller with just
*.edit.organizational could read every org's records by omitting or spoofing
the param. _generali_scope_where now derives the visibility clause from the
caller's GRANTS, never the request.
"""

import nx_lib.views.generali as gv


def _scope(app, monkeypatch, perms, session_org, session_uid, requested_org, org_users):
    monkeypatch.setattr(gv, "has_permission", lambda code: code in perms)
    monkeypatch.setattr(gv, "_generali_userids_in_org", lambda oc: org_users.get(oc, []))
    with app.test_request_context():
        from flask import session

        session["organizationcode"] = session_org
        session["userid"] = session_uid
        return gv._generali_scope_where("generali.reporting", "ReportByUserID", requested_org)


def test_transorg_no_request_org_is_unconstrained(app, monkeypatch):
    clauses, params = _scope(
        app, monkeypatch, {"generali.reporting.edit.transorganizational"}, "A", "u1", "", {}
    )
    assert clauses == []
    assert params == []


def test_transorg_honours_requested_org(app, monkeypatch):
    clauses, params = _scope(
        app,
        monkeypatch,
        {"generali.reporting.edit.transorganizational"},
        "A",
        "u1",
        "B",
        {"B": [10, 11]},
    )
    assert clauses == ["ReportByUserID IN (?,?)"]
    assert params == [10, 11]


def test_org_only_ignores_requested_org_and_clamps_to_session_org(app, monkeypatch):
    """The core fix: a caller holding only *.edit.organizational who requests a
    RIVAL org must be clamped to their OWN session org, never the requested
    one."""
    clauses, params = _scope(
        app,
        monkeypatch,
        {"generali.reporting.edit.organizational"},
        "A",
        "u1",
        "B",  # requests rival org B
        {"A": [1, 2], "B": [10, 11]},
    )
    assert clauses == ["ReportByUserID IN (?,?)"]
    assert params == [1, 2]  # org A's users, NOT B's


def test_neither_grant_clamps_to_own_userid(app, monkeypatch):
    clauses, params = _scope(app, monkeypatch, set(), "A", "u1", "", {})
    assert clauses == ["ReportByUserID = ?"]
    assert params == ["u1"]


def test_empty_org_fails_closed(app, monkeypatch):
    """An org that resolves to no users must NOT drop the constraint (which
    would return every org's rows) -- it fails closed to zero rows."""
    clauses, params = _scope(
        app, monkeypatch, {"generali.reporting.edit.organizational"}, "A", "u1", "", {"A": []}
    )
    assert clauses == ["1=0"]
    assert params == []
