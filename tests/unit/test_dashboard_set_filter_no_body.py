"""Unit test for a strict_optional-driven fix in dashboard_set_filter.

A POST with no JSON body (or a non-JSON content type) makes ``request.json``
None; calling ``.get()`` on it crashed with an unhandled AttributeError (500)
instead of falling back to "all" like an explicit ``{}`` body already does.
"""

from nx_lib.views.dashboard import dashboard_set_filter


def test_set_filter_with_no_json_body_falls_back_to_all(app):
    with app.test_request_context(
        "/api/dashboard/set_filter",
        method="POST",
        # No `json=` / no body at all -- request.get_json(silent=True) is None.
    ):
        from flask import session

        session["username"] = "user@test.local"
        session["permissions"] = ["dashboard.view"]

        resp = dashboard_set_filter()

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["process_name"] == "all"
