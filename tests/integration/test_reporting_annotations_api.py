"""Integration: /api/reporting/reports/<id>/annotations (#284)."""

from nx_lib.views.reporting.reports import _can_view_report


def _create_report(client, name="Annotation Test"):
    resp = client.post(
        "/api/reporting/reports",
        json={
            "name": name,
            "definition": {
                "kind": "sql",
                "target": "statistics",
                "sql": "SELECT 1 AS one",
                "title": name,
            },
        },
    )
    assert resp.status_code == 200, resp.data
    return resp.get_json()["id"]


def _userid(client):
    with client.session_transaction() as s:
        return s["userid"]


def test_can_view_report_owner_shared_and_granted(admin_client, login):
    rid = _create_report(admin_client)
    try:
        owner = _userid(admin_client)
        assert _can_view_report(rid, owner) is True

        other_client = login(username="noai@test.local")
        other = _userid(other_client)
        assert _can_view_report(rid, other) is False

        admin_client = login(username="admin@test.local")
        admin_client.post(f"/api/reporting/reports/{rid}/shares", json={"visibility": "shared"})
        assert _can_view_report(rid, other) is True
    finally:
        admin_client = login(username="admin@test.local")
        admin_client.delete(f"/api/reporting/reports/{rid}")
