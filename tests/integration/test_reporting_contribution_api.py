"""Integration: POST /api/reporting/contribution (contribution analysis)."""

import pytest

from nx_lib.db import engine_nexora_db

SOURCE = {
    "code": "contrib_test_src",
    "kind": "curated",
    "label": "Contrib Test Src",
    "permission": "reporting.source.docprocessing.use",
    "provider": "table",
    "engine": "nexora",
    "baseObject": "dbo.Users",
    "columns": [
        {
            "field": "Email",
            "label": "Email",
            "type": "string",
            "filterable": True,
            "sortable": True,
            "grainable": False,
        },
        {
            "field": "locale",
            "label": "Locale",
            "type": "string",
            "filterable": True,
            "sortable": True,
            "grainable": False,
        },
        {
            "field": "LastLoginAt",
            "label": "Last Login",
            "type": "datetime",
            "filterable": True,
            "sortable": True,
            "grainable": True,
        },
    ],
    "enabled": True,
    "sortOrder": 18,
}


@pytest.fixture
def contrib_source(admin_client):
    src = admin_client.post("/api/reporting/admin/sources", json=SOURCE).get_json()["id"]
    met = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "contrib_test_count",
            "sourceId": "contrib_test_src",
            "label": "Users",
            "aggregation": "count",
            "enabled": True,
            "sortOrder": 18,
        },
    ).get_json()["id"]
    yield "contrib_test_src"
    admin_client.delete(f"/api/reporting/admin/metrics/{met}")
    admin_client.delete(f"/api/reporting/admin/sources/{src}")


def _definition(filters):
    return {
        "schemaVersion": 1,
        "source": "contrib_test_src",
        "visualization": "table",
        "title": "Contrib",
        "columns": [],
        "filters": filters,
        "sort": [],
        "scope": {},
        "rowLimit": 10,
        "metrics": [{"metric": "contrib_test_count"}],
    }


TOKEN_FILTER = {"field": "LastLoginAt", "op": "between", "value": {"token": "this_year"}}


def test_contribution_invalid_json_400(admin_client):
    resp = admin_client.post("/api/reporting/contribution", data="nope")
    assert resp.status_code == 400


def test_contribution_without_metrics_400(admin_client, contrib_source):
    rd = _definition([TOKEN_FILTER])
    rd["metrics"] = []
    resp = admin_client.post("/api/reporting/contribution", json=rd)
    assert resp.status_code == 400
    assert "measure" in resp.get_json()["error"]


def test_contribution_without_token_window_400(admin_client, contrib_source):
    resp = admin_client.post("/api/reporting/contribution", json=_definition([]))
    assert resp.status_code == 400
    assert "comparison window" in resp.get_json()["error"]


def test_contribution_shape_and_totals_match_run(admin_client, contrib_source):
    rd = _definition([TOKEN_FILTER])
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.Users SET LastLoginAt = GETDATE() WHERE Email = ?",
            ("admin@test.local",),
        )
        conn.commit()

        resp = admin_client.post("/api/reporting/contribution", json=rd)
        assert resp.status_code == 200, resp.data
        body = resp.get_json()
        assert set(body) >= {
            "priorStart",
            "priorEnd",
            "metric",
            "metricLabel",
            "isRatio",
            "currentTotal",
            "priorTotal",
            "dimensions",
            "skipped",
        }
        assert body["metric"] == "contrib_test_count" and body["isRatio"] is False
        # string columns in catalog order, no processname on a table source
        assert [d["field"] for d in body["dimensions"]] == ["Email", "locale"]
        assert body["dimensions"][0]["label"] == "Email"
        assert body["dimensions"][0]["rows"]  # non-vacuous: at least one contributor
        for row in body["dimensions"][0]["rows"]:
            assert set(row) == {"value", "current", "prior", "delta", "share"}
        # D3: header total is the zero-column run's grand total
        run = admin_client.post("/api/reporting/run", json=rd).get_json()
        assert body["currentTotal"] == float(run["rows"][0][0])
    finally:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.Users SET LastLoginAt = NULL WHERE Email = ?",
            ("admin@test.local",),
        )
        conn.commit()
        conn.close()


def test_contribution_malformed_token_400(admin_client, contrib_source):
    bad_filter = {"field": "LastLoginAt", "op": "between", "value": {"token": "bogus"}}
    resp = admin_client.post("/api/reporting/contribution", json=_definition([bad_filter]))
    assert resp.status_code == 400


def test_contribution_eq_filter_drops_that_dimension(admin_client, contrib_source):
    rd = _definition([TOKEN_FILTER, {"field": "locale", "op": "eq", "value": "de"}])
    body = admin_client.post("/api/reporting/contribution", json=rd).get_json()
    assert [d["field"] for d in body["dimensions"]] == ["Email"]


def test_contribution_without_permission_403(contrib_source, user_client):
    resp = user_client.post("/api/reporting/contribution", json=_definition([TOKEN_FILTER]))
    assert resp.status_code == 403  # require_permission("reporting.view") denies user@test.local
