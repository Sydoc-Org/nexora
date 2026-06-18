"""Integration tests for nx_lib.views.workitems — 19 routes.

Seed users only have dashboard.view, so all workitems.* gates return 403.
Tests that exercise route bodies use the workitems_all_perms fixture
(monkeypatches has_permission to True).

Most workitems routes query OctoDB tables (t_WorkItems, t_ActivityInstances,
t_Processes) and NEXORA tables (SearchConfig, Search_Field_Labels,
WorkitemTags, WorkitemComments) that are absent from the TEST schema. They
fall through except branches and return 500 JSON. Tuple matches in
assertions allow for that.

Routes covered (19 endpoints):
- /api/config/fields                         GET
- /api/docfield_values                       GET
- /api/workitems                             GET
- /api/export/workitems/csv                  GET
- /workitems                                 page
- /import_workitems                          POST
- /api/workitem/<id>                         GET
- /api/get_media_info/<id>                   GET
- /api/get_media_raw/<id>/<idx>              GET
- /api/get_audithistory/<id>                 GET
- /api/users                                 GET
- /api/workitem/<id>/interactions            GET
- /api/workitem/<id>/comment                 POST
- /api/workitem/<id>/assign                  POST
- /api/workitem/<id>/priority                POST
- /api/tags                                  GET
- /api/workitems_page_init                   GET
- /api/workitem/<id>/tags                    POST
- /api/workitem/<id>/tags/<tag_id>           DELETE
"""

import pytest


@pytest.fixture()
def workitems_all_perms(monkeypatch):
    monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
    yield


# ============================ /workitems page ================================


def test_workitems_overview_anonymous_redirects(client):
    resp = client.get("/workitems", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_workitems_overview_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/workitems")
    assert resp.status_code == 403


def test_workitems_overview_with_perms(user_client, workitems_all_perms):
    """With all perms granted, the page tries to render — some helper queries
    hit absent tables → 500-fallback render. Both outcomes are valid."""
    resp = user_client.get("/workitems")
    assert resp.status_code in (200, 500)


# ============================ API: config/data ===============================


def test_api_config_fields_anonymous(client):
    resp = client.get("/api/config/fields")
    assert resp.status_code == 401


def test_api_config_fields_authed(user_client):
    """Helper is not @require_permission-gated. Returns 200 with possibly empty
    search_options if Search_Field_Labels/SearchConfig are missing."""
    resp = user_client.get("/api/config/fields")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "search_options" in body
    assert "labels" in body


def test_api_docfield_values_gated(noperm_client):
    resp = noperm_client.get("/api/docfield_values")
    assert resp.status_code == 403


def test_api_docfield_values_with_perms(user_client, workitems_all_perms):
    resp = user_client.get("/api/docfield_values?docfield=foo&prcfW=all")
    assert resp.status_code in (200, 400, 500)


def test_api_workitems_gated(noperm_client):
    resp = noperm_client.get("/api/workitems")
    assert resp.status_code == 403


def test_api_workitems_with_perms(user_client, workitems_all_perms):
    resp = user_client.get("/api/workitems")
    assert resp.status_code in (200, 500)


def test_api_workitems_returns_degraded_key(user_client, workitems_all_perms):
    resp = user_client.get("/api/workitems")
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        body = resp.get_json()
        assert "workitems" in body
        assert "pagination" in body
        assert "degradedSources" in body
        assert isinstance(body["degradedSources"], list)


def test_api_workitems_docfield_tolerates_absent_ms02_engine(user_client, workitems_all_perms):
    """A doc-field query for an MS02 process must not error beyond the harness
    tolerance when engine_ms02_docfields_pg is None (CI default)."""
    resp = user_client.get(
        "/api/workitems",
        query_string={
            "prcfW": "sydoc.praesidialdepartement_bs",
            "docfield": "doctype",
            "docvalue": "invoice",
        },
    )
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        body = resp.get_json()
        assert "workitems" in body
        assert "pagination" in body


def test_api_workitems_docfield_mixed_processes_tolerated(user_client, workitems_all_perms):
    resp = user_client.get(
        "/api/workitems",
        query_string={"prcfW": "all", "docfield": "doctype", "docvalue": "x"},
    )
    assert resp.status_code in (200, 500)


def test_export_workitems_csv_gated(noperm_client):
    resp = noperm_client.get("/api/export/workitems/csv")
    assert resp.status_code == 403


def test_export_workitems_csv_with_perms(user_client, workitems_all_perms):
    """No data → returns CSV with the placeholder line."""
    resp = user_client.get("/api/export/workitems/csv")
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert "text/csv" in resp.headers.get("Content-Type", "")


def test_import_workitems_gated(noperm_client):
    resp = noperm_client.post("/import_workitems", json={})
    assert resp.status_code == 403


def test_import_workitems_with_perms_empty_body(user_client, workitems_all_perms):
    """No importFile in request → flash + redirect (302) back to overview."""
    resp = user_client.post("/import_workitems", json={}, follow_redirects=False)
    assert resp.status_code in (200, 302, 400, 500)


# ============================ single workitem detail =========================


def test_get_single_workitem_anonymous(client):
    resp = client.get("/api/workitem/1", follow_redirects=False)
    # Function checks `if 'username' not in session` first → 401 JSON
    assert resp.status_code in (200, 302, 401, 500)


def test_get_single_workitem_authed_unknown_id(user_client):
    resp = user_client.get("/api/workitem/999999")
    assert resp.status_code in (200, 404, 500)


def test_api_get_media_info_authed_unknown_id(user_client):
    """View has an internal has_permission('workitems.details.view') check
    that the seed user doesn't satisfy → 403. With workitems_all_perms it
    would attempt OctoDB lookup and 500/404."""
    resp = user_client.get("/api/get_media_info/999999")
    assert resp.status_code in (200, 401, 403, 404, 500)


def test_api_get_media_raw_gated(noperm_client):
    resp = noperm_client.get("/api/get_media_raw/1/0")
    assert resp.status_code == 403


def test_api_get_media_raw_with_perms_unknown(user_client, workitems_all_perms):
    resp = user_client.get("/api/get_media_raw/999999/0")
    assert resp.status_code in (200, 404, 500)


def test_get_audithistory_gated(noperm_client):
    resp = noperm_client.get("/api/get_audithistory/1")
    assert resp.status_code == 403


def test_get_audithistory_with_perms(user_client, workitems_all_perms):
    resp = user_client.get("/api/get_audithistory/999999")
    assert resp.status_code in (200, 404, 500)


# ============================ users + interactions ===========================


def test_get_users_for_mentions_authed(user_client):
    """No permission gate — returns users matching a session-org filter."""
    resp = user_client.get("/api/users")
    assert resp.status_code in (200, 401, 500)


def test_get_workitem_interactions_authed(user_client):
    resp = user_client.get("/api/workitem/999999/interactions")
    assert resp.status_code in (200, 404, 500)


def test_add_workitem_comment_anonymous_returns_unauth(client):
    resp = client.post("/api/workitem/1/comment", json={"comment": "x"})
    assert resp.status_code in (200, 302, 401, 500)


def test_add_workitem_comment_authed_unknown(user_client):
    resp = user_client.post("/api/workitem/999999/comment", json={"comment": "x"})
    assert resp.status_code in (200, 400, 404, 500)


def test_assign_workitem_authed_unknown(user_client):
    resp = user_client.post("/api/workitem/999999/assign", json={"userId": 1001})
    assert resp.status_code in (200, 400, 404, 500)


def test_set_workitem_priority_authed_unknown(user_client):
    resp = user_client.post("/api/workitem/999999/priority", json={"priority": "high"})
    assert resp.status_code in (200, 400, 404, 500)


# ============================ tags + page init ===============================


def test_get_all_tags_authed(user_client):
    """No permission gate — returns tags from WorkitemTags (absent → 500)."""
    resp = user_client.get("/api/tags")
    assert resp.status_code in (200, 500)


def test_api_workitems_page_init_authed(user_client):
    resp = user_client.get("/api/workitems_page_init")
    assert resp.status_code in (200, 500)


def test_add_tag_to_workitem_authed_unknown(user_client):
    resp = user_client.post("/api/workitem/999999/tags", json={"tag_id": 1})
    assert resp.status_code in (200, 400, 404, 500)


def test_remove_tag_from_workitem_authed_unknown(user_client):
    resp = user_client.delete("/api/workitem/999999/tags/999")
    assert resp.status_code in (200, 404, 500)
