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


def test_annotations_without_reporting_perm_403(user_client):
    assert user_client.get("/api/reporting/reports/1/annotations").status_code == 403


def test_annotation_crud_owner(admin_client):
    rid = _create_report(admin_client)
    try:
        assert admin_client.get(f"/api/reporting/reports/{rid}/annotations").get_json() == []
        cr = admin_client.post(
            f"/api/reporting/reports/{rid}/annotations",
            json={"bucket": "2026-09-01", "text": "  Mailroom outage  "},
        )
        assert cr.status_code == 200, cr.data
        aid = cr.get_json()["id"]
        lst = admin_client.get(f"/api/reporting/reports/{rid}/annotations").get_json()
        assert len(lst) == 1
        assert lst[0]["id"] == aid
        assert lst[0]["bucket"] == "2026-09-01"
        assert lst[0]["text"] == "Mailroom outage"
        assert lst[0]["author"]
        assert lst[0]["createdAt"]
        assert (
            admin_client.delete(f"/api/reporting/reports/{rid}/annotations/{aid}").status_code
            == 200
        )
        assert admin_client.get(f"/api/reporting/reports/{rid}/annotations").get_json() == []
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_annotation_validation_400(admin_client):
    rid = _create_report(admin_client)
    try:
        url = f"/api/reporting/reports/{rid}/annotations"
        assert (
            admin_client.post(url, json={"bucket": "2026-09-01", "text": "   "}).status_code == 400
        )
        assert admin_client.post(url, json={"bucket": "", "text": "x"}).status_code == 400
        assert (
            admin_client.post(url, json={"bucket": "2026-09-01", "text": "x" * 501}).status_code
            == 400
        )
        assert admin_client.post(url, json={"bucket": "b" * 65, "text": "x"}).status_code == 400
        assert (
            admin_client.post(url, json={"bucket": "2026-09-01", "text": "x" * 500}).status_code
            == 200
        )
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid}")


def test_annotation_non_owner_reads_shared_but_cannot_write(admin_client, login):
    rid = _create_report(admin_client)
    try:
        cr = admin_client.post(
            f"/api/reporting/reports/{rid}/annotations",
            json={"bucket": "2026-09-01", "text": "owner note"},
        )
        aid = cr.get_json()["id"]
        admin_client.post(f"/api/reporting/reports/{rid}/shares", json={"visibility": "shared"})

        other = login(username="noai@test.local")
        assert other.get(f"/api/reporting/reports/{rid}/annotations").status_code == 200
        assert (
            other.post(
                f"/api/reporting/reports/{rid}/annotations",
                json={"bucket": "2026-09-01", "text": "intruder"},
            ).status_code
            == 404
        )
        assert other.delete(f"/api/reporting/reports/{rid}/annotations/{aid}").status_code == 404
    finally:
        admin = login(username="admin@test.local")
        admin.delete(f"/api/reporting/reports/{rid}")


def test_annotation_private_report_hidden_from_non_owner(admin_client, login):
    rid = _create_report(admin_client)
    try:
        other = login(username="noai@test.local")
        assert other.get(f"/api/reporting/reports/{rid}/annotations").status_code == 404
    finally:
        admin = login(username="admin@test.local")
        admin.delete(f"/api/reporting/reports/{rid}")


def test_annotation_delete_foreign_id_404(admin_client):
    rid_a = _create_report(admin_client, "A")
    rid_b = _create_report(admin_client, "B")
    try:
        aid = admin_client.post(
            f"/api/reporting/reports/{rid_a}/annotations",
            json={"bucket": "2026-09-01", "text": "on A"},
        ).get_json()["id"]
        assert (
            admin_client.delete(f"/api/reporting/reports/{rid_b}/annotations/{aid}").status_code
            == 404
        )
        assert len(admin_client.get(f"/api/reporting/reports/{rid_a}/annotations").get_json()) == 1
    finally:
        admin_client.delete(f"/api/reporting/reports/{rid_a}")
        admin_client.delete(f"/api/reporting/reports/{rid_b}")


def test_annotation_cascades_with_report(admin_client):
    from sqlalchemy import text

    from nx_lib.db import engine_nexora_db

    rid = _create_report(admin_client)
    admin_client.post(
        f"/api/reporting/reports/{rid}/annotations",
        json={"bucket": "2026-09-01", "text": "gone with the report"},
    )
    admin_client.delete(f"/api/reporting/reports/{rid}")
    with engine_nexora_db.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM dbo.ReportAnnotations WHERE ReportID = :r"), {"r": rid}
        ).scalar()
    assert n == 0
