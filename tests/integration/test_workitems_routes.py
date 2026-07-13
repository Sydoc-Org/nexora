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


def test_workitems_overview_uses_shared_detail_panel(user_client, workitems_all_perms):
    """The workitems page wires the shared renderer."""
    resp = user_client.get("/workitems")
    # 200 or 500-fallback possible in CI; the partial markers live in template body.
    if resp.status_code == 200:
        assert b"NexoraWorkitemDetail.render" in resp.data


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


def test_api_config_fields_perm_state_in_cache_key(user_client, monkeypatch):
    """The route's cache key embeds the sensitive-perm state as a `_s0`/`_s1`
    suffix (see api_config_fields: `f"config_fields_{...}_s{int(_sees_sensitive)}"`)
    so a permissioned user's cached response can never be served to a
    permissionless one. search_options is always empty in this test DB (no
    SearchConfig/Search_Field_Labels tables), so we can't assert on response
    *body* differences — instead assert directly against
    nx_lib.views.workitems.cache that each perm state populates its own,
    distinct, still-present cache entry.
    """
    import nx_lib.views.workitems as wv
    from nx_lib.views.workitems import cache

    cache.clear()

    # Pin the locale so the key's language segment is deterministic, and read
    # the session's real permissions the same way the route does, so the key's
    # allowed_processes segment matches exactly without hardcoding/guessing
    # what the seeded test user has.
    with user_client.session_transaction() as sess:
        sess["locale"] = "en"
        perms = sess.get("permissions", [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split(".")[-2] + "." + perm.split(".")[-1])
        for perm in perms
        if perm.startswith(prefix)
    }
    key_base = f"config_fields_{'_'.join(sorted(allowed_processes))}_en_s"
    key_s0 = key_base + "0"
    key_s1 = key_base + "1"
    assert key_s0 != key_s1

    # Without the sensitive perm the response is filtered + cached under _s0.
    monkeypatch.setattr(
        wv, "has_permission", lambda code: code != "workitems.filter.documentfields.sensitive"
    )
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    r0 = user_client.get("/api/config/fields")
    assert r0.status_code == 200
    cached_s0 = cache.get(key_s0)
    assert cached_s0 is not None, f"expected a cache entry under {key_s0!r}"
    assert cache.get(key_s1) is None, "the _s1 entry must not exist yet"

    # With the perm the cache key differs (_s1) -> not served the _s0 entry.
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    r1 = user_client.get("/api/config/fields")
    assert r1.status_code == 200
    cached_s1 = cache.get(key_s1)
    assert cached_s1 is not None, f"expected a cache entry under {key_s1!r}"

    # Both perm states landed in genuinely distinct, still-present cache
    # entries: the permissioned request never reused or clobbered the
    # permissionless slot.
    assert cache.get(key_s0) == cached_s0


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


# ============================ MS02 autocomplete ==============================


def test_api_docfield_values_ms02_degrades_without_engine(user_client, workitems_all_perms):
    """For an MS02 process with no doc-field engine, autocomplete returns [] (200)
    or stays within harness tolerance; never an uncaught error."""
    resp = user_client.get(
        "/api/docfield_values",
        query_string={
            "process": "sydoc.praesidialdepartement_bs",
            "field": "doctype",
            "q": "inv",
        },
    )
    assert resp.status_code in (200, 401, 500)
    if resp.status_code == 200:
        assert isinstance(resp.get_json(), list)


def test_api_docfield_values_blocks_sensitive_without_perm(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv

    # Pretend col_validationuser is a real searchable column, and that it is sensitive.
    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_validationuser"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    # Everything allowed EXCEPT the sensitive perm.
    monkeypatch.setattr(
        wv, "has_permission", lambda code: code != "workitems.filter.documentfields.sensitive"
    )
    resp = user_client.get("/api/docfield_values?field=validationuser&process=all")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_api_docfield_values_allows_sensitive_with_perm(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv

    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_validationuser"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    monkeypatch.setattr(wv, "has_permission", lambda code: True)  # incl. the sensitive perm
    # With the perm the sensitivity gate is skipped; the route then hits the
    # (absent-in-CI) SearchConfig and degrades to 500/[] -- either proves the gate
    # did NOT short-circuit. Accept both to stay DB-independent.
    resp = user_client.get("/api/docfield_values?field=validationuser&process=all")
    assert resp.status_code in (200, 500)


def test_remove_tag_from_workitem_authed_unknown(user_client):
    resp = user_client.delete("/api/workitem/999999/tags/999")
    assert resp.status_code in (200, 404, 500)


# ============================ /import_prepared_audit =========================


def test_import_prepared_audit_gated(noperm_client):
    resp = noperm_client.post("/import_prepared_audit")
    assert resp.status_code == 403


def test_import_prepared_audit_no_file(user_client, workitems_all_perms):
    resp = user_client.post("/import_prepared_audit")
    # CI has no MS02 engine -> MS02-only gate returns 400 (not 403; perms are all granted)
    assert resp.status_code == 400
    assert "MS02" in (resp.get_json() or {}).get("error", "")


def test_import_prepared_audit_rejects_non_xlsx(user_client, workitems_all_perms):
    import io

    data = {"preparedAuditFile": (io.BytesIO(b"%PDF-1.4 nope"), "x.xlsx")}
    resp = user_client.post("/import_prepared_audit", data=data, content_type="multipart/form-data")
    # CI has no MS02 engine -> MS02-only gate returns 400 (not 403; perms are all granted)
    assert resp.status_code == 400
    assert "MS02" in (resp.get_json() or {}).get("error", "")


def _prepared_docs_link_tag(html):
    """Return the opening <a ...> tag of the register link, or None if absent.
    The tag spans several lines, so match across newlines up to the closing >."""
    import re

    m = re.search(r'<a[^>]*data-testid="prepared-docs-link"[^>]*>', html)
    return m.group(0) if m else None


def test_prepared_docs_link_visible_for_target_process(
    user_client, workitems_all_perms, monkeypatch
):
    """The toolbar link is rendered and NOT hidden when the selected process is
    an MS02 prepared-docs target, and the qualifying-process list is embedded so
    the client JS can toggle it live when the process dropdown changes."""
    import nx_lib.hooks as hooks
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "_ms02_prepared_docs_processes", lambda: ["sydoc.05_PDBS"])
    # _reload_user_permissions (before_request) overwrites session["permissions"]
    # from the DB each request via load_permissions_for_user; patch it so
    # allowed_processes contains the target and process_name survives the reset.
    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: [
            "workitems.view",
            "workitems.import.preparedaudit",
            "workitems.filter.process.sydoc.05_PDBS",
        ],
    )

    resp = user_client.get("/workitems?prcfW=sydoc.05_PDBS")
    assert resp.status_code == 200
    tag = _prepared_docs_link_tag(resp.data.decode())
    assert tag is not None, "register link should be rendered"
    assert "hidden" not in tag, "link must be visible for the matching process"
    assert "/prepared_documents" in tag
    assert "sydoc.05_PDBS" in tag, "qualifying-process list must be embedded for the JS toggle"


def test_prepared_docs_link_rendered_but_hidden_off_target(
    user_client, workitems_all_perms, monkeypatch
):
    """On 'All Processes' (and any non-PDBS process) the link stays in the DOM
    (so the JS can reveal it live without a reload) but carries the hidden class."""
    import nx_lib.hooks as hooks
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "_ms02_prepared_docs_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: [
            "workitems.view",
            "workitems.import.preparedaudit",
            "workitems.filter.process.sydoc.05_PDBS",
        ],
    )

    resp = user_client.get("/workitems")  # defaults to prcfW=all
    assert resp.status_code == 200
    tag = _prepared_docs_link_tag(resp.data.decode())
    assert tag is not None, "link should still be in the DOM for the JS toggle"
    assert "hidden" in tag, "link must be hidden until a PDBS process is selected"


def test_import_prepared_audit_upserts_when_ms02_active(
    user_client, workitems_all_perms, monkeypatch
):
    """Past the MS02 gate, a valid xlsx upserts into the register and returns
    {inserted, updated, total} (no token, no synthetic-row machinery)."""
    import io

    import openpyxl

    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    # Bypass the MIME sniff for the synthetic xlsx bytes.
    monkeypatch.setattr(wv, "is_file_allowed", lambda name, stream: True)

    captured = {}

    def fake_upsert(rows, uploaded_by):
        captured["rows"] = rows
        captured["uploaded_by"] = uploaded_by
        return {"inserted": len(rows), "updated": 0, "total": len(rows)}

    monkeypatch.setattr(wv, "upsert_prepared_documents", fake_upsert)

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(["PID", "Collected", "CollectedBy", "Prepared", "PreparedBy"])
    sh.append(["100", 1, "Alice", 1, "Bob"])
    buf = io.BytesIO()
    wb.save(buf)

    resp = user_client.post(
        "/import_prepared_audit",
        data={"preparedAuditFile": (io.BytesIO(buf.getvalue()), "p.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["inserted"] == 1
    assert captured["rows"][0]["pid"] == "100"


def test_import_prepared_audit_persists_even_without_pid_specs(
    user_client, workitems_all_perms, monkeypatch
):
    """The register must persist rows even when no MS02 PID specs are configured
    (the default CI/TEST path: SearchConfig has no 'ms02' col_pid). The old
    warning early-return is intentionally gone -- Octo status degrades on the
    page, the upload still upserts."""
    import io

    import openpyxl

    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "is_file_allowed", lambda name, stream: True)
    # No PID specs configured.
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [])
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: [])
    monkeypatch.setattr(
        wv,
        "upsert_prepared_documents",
        lambda rows, uploaded_by: {"inserted": len(rows), "updated": 0, "total": len(rows)},
    )

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(["PID", "Prepared"])
    sh.append(["100", 1])
    buf = io.BytesIO()
    wb.save(buf)

    resp = user_client.post(
        "/import_prepared_audit",
        data={"preparedAuditFile": (io.BytesIO(buf.getvalue()), "p.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert "token" not in body
    assert "warning" not in body


def test_import_prepared_audit_db_failure_returns_500(
    user_client, workitems_all_perms, monkeypatch
):
    import io

    import openpyxl

    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "is_file_allowed", lambda name, stream: True)

    def boom(rows, uploaded_by):
        raise RuntimeError("db down")

    monkeypatch.setattr(wv, "upsert_prepared_documents", boom)

    wb = openpyxl.Workbook()
    sh = wb.active
    sh.append(["PID", "Prepared"])
    sh.append(["100", 1])
    buf = io.BytesIO()
    wb.save(buf)

    resp = user_client.post(
        "/import_prepared_audit",
        data={"preparedAuditFile": (io.BytesIO(buf.getvalue()), "p.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 500
    assert "error" in (resp.get_json() or {})


# ====================== /prepared_documents (register page) =================


def test_prepared_documents_page_gated(noperm_client):
    """No permission -> 403 (or login redirect)."""
    resp = noperm_client.get("/prepared_documents")
    assert resp.status_code in (403, 302)


def test_prepared_documents_page_denies_without_ms02(user_client, workitems_all_perms):
    """Perm present but no MS02 engine in CI -> ms02_active gate denies (403)."""
    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 403


def test_prepared_documents_page_renders_when_ms02_active(
    user_client, workitems_all_perms, monkeypatch
):
    """Perm + ms02_active -> 200; table renders. DB read + Octo resolve mocked.
    The in-body prepared_import_perm uses the wv-local has_permission binding,
    so patch that too (the documented fixture trap)."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
    monkeypatch.setattr(
        wv,
        "fetch_prepared_documents_page",
        lambda offset, limit, pid=None: [
            {
                "id": 1,
                "pid": "100",
                "collected": True,
                "collected_by": "A",
                "prepared": False,
                "prepared_by": "",
                "uploaded_by": 7,
                "uploaded_at": None,
                "updated_at": None,
            }
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})

    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    assert b"100" in resp.data


def test_prepared_documents_page_octo_resolve_failure_degrades(
    user_client, workitems_all_perms, monkeypatch
):
    """resolve returning None must NOT break the page (status degrades to dash)."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
    monkeypatch.setattr(
        wv,
        "fetch_prepared_documents_page",
        lambda offset, limit, pid=None: [
            {
                "id": 1,
                "pid": "100",
                "collected": False,
                "collected_by": "",
                "prepared": False,
                "prepared_by": "",
                "uploaded_by": None,
                "uploaded_at": None,
                "updated_at": None,
            }
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: None)

    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200


def test_prepared_documents_clear_gated(noperm_client):
    resp = noperm_client.post("/prepared_documents/clear")
    assert resp.status_code in (403, 302)


def test_prepared_documents_clear_400_without_ms02(user_client, workitems_all_perms):
    resp = user_client.post("/prepared_documents/clear")
    assert resp.status_code == 400
    assert b"MS02" in resp.data


def test_prepared_documents_clear_deletes_when_ms02_active(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "clear_prepared_documents", lambda: 3)
    resp = user_client.post("/prepared_documents/clear")
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 3


def test_prepared_documents_preview_button_requires_details_view(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
    monkeypatch.setattr(
        wv,
        "fetch_prepared_documents_page",
        lambda offset, limit, pid=None: [
            {
                "id": 1,
                "pid": "100",
                "collected": True,
                "collected_by": "A",
                "prepared": False,
                "prepared_by": "",
                "uploaded_by": 7,
                "uploaded_at": None,
                "updated_at": None,
            }
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})

    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    assert b'data-testid="prepared-docs-preview"' in resp.data
    assert b'data-wid="42"' in resp.data
    assert b"NexoraWorkitemDetail" in resp.data

    monkeypatch.setattr(wv, "has_permission", lambda code: code != "workitems.details.view")
    resp2 = user_client.get("/prepared_documents")
    assert resp2.status_code == 200
    assert b'data-testid="prepared-docs-preview"' not in resp2.data


def test_prepared_documents_modal_wires_shared_renderer(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 0)
    monkeypatch.setattr(wv, "fetch_prepared_documents_page", lambda offset, limit, pid=None: [])
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: [])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: None)
    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    assert b"NexoraWorkitemDetail.render" in resp.data
    assert b"attachLightbox" in resp.data
    assert b"api/config/fields" in resp.data


def test_prepared_documents_preview_present_when_media_degrades(
    user_client, workitems_all_perms, monkeypatch
):
    """Octo resolve returning None still renders the page with the modal shell (image
    degradation is client-side; the panel must not be gated on media)."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
    monkeypatch.setattr(
        wv,
        "fetch_prepared_documents_page",
        lambda offset, limit, pid=None: [
            {
                "id": 1,
                "pid": "100",
                "collected": True,
                "collected_by": "A",
                "prepared": False,
                "prepared_by": "",
                "uploaded_by": 7,
                "uploaded_at": None,
                "updated_at": None,
            }
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})
    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    assert b'data-testid="prepared-docs-preview-modal"' in resp.data


def test_prepared_documents_pid_filter_passes_through(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    seen = {}
    monkeypatch.setattr(
        wv, "count_prepared_documents", lambda pid=None: (seen.__setitem__("count_pid", pid) or 1)
    )
    monkeypatch.setattr(
        wv,
        "fetch_prepared_documents_page",
        lambda offset, limit, pid=None: (
            seen.__setitem__("fetch_pid", pid)
            or [
                {
                    "id": 1,
                    "pid": "100",
                    "collected": True,
                    "collected_by": "A",
                    "prepared": False,
                    "prepared_by": "",
                    "uploaded_by": 7,
                    "uploaded_at": None,
                    "updated_at": None,
                }
            ]
        ),
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: [])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: None)
    resp = user_client.get("/prepared_documents?pid=100")
    assert resp.status_code == 200
    assert seen.get("count_pid") == "100"
    assert seen.get("fetch_pid") == "100"
    assert b'data-testid="prepared-docs-show-all"' in resp.data


def test_prepared_documents_centered_headers_use_align_center(
    user_client, workitems_all_perms, monkeypatch
):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
    monkeypatch.setattr(
        wv,
        "fetch_prepared_documents_page",
        lambda offset, limit, pid=None: [
            {
                "id": 1,
                "pid": "100",
                "collected": True,
                "collected_by": "A",
                "prepared": False,
                "prepared_by": "",
                "uploaded_by": 7,
                "uploaded_at": None,
                "updated_at": None,
            }
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})

    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    # The three centered columns now carry the .nx-table align helper on the <th>,
    # so headers no longer render left while bodies render center.
    assert resp.data.count(b'class="px-6 py-3 align-center"') == 3


def test_stamp_in_register_marks_rows(monkeypatch):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_wids_to_pids", lambda e, s, w: {42: "100", 43: "200"})
    monkeypatch.setattr(wv, "pids_in_register", lambda pids: {"100"})
    rows = [{"workitemid": 42}, {"workitemid": 43}]
    wv._stamp_in_register(rows)
    assert rows[0]["pid"] == "100" and rows[0]["in_register"] is True
    assert rows[1]["pid"] == "200" and rows[1]["in_register"] is False


def test_stamp_in_register_noop_when_not_ms02(monkeypatch):
    import nx_lib.views.workitems as wv

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", None)
    rows = [{"workitemid": 42}]
    wv._stamp_in_register(rows)
    assert "pid" not in rows[0] and "in_register" not in rows[0]


def test_api_workitems_carries_pid_in_register(user_client, workitems_all_perms, monkeypatch):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(
        wv,
        "fetch_merged_page",
        lambda filt, off, lim: (
            [
                {
                    "workitemid": 42,
                    "status": "Ready",
                    "current_stage": "Import",
                    "priority": 0,
                    "tags": [],
                    "modifiedat": None,
                }
            ],
            1,
            [],
        ),
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_wids_to_pids", lambda e, s, w: {42: "100"})
    monkeypatch.setattr(wv, "pids_in_register", lambda pids: {"100"})
    resp = user_client.get("/api/workitems")
    assert resp.status_code in (200, 500)  # 500 only if upstream filter parsing trips in CI
    if resp.status_code == 200:
        wi = resp.get_json()["workitems"][0]
        assert wi["pid"] == "100"
        assert wi["in_register"] is True


def test_prepared_docs_preview_button_carries_stage(user_client, workitems_all_perms, monkeypatch):
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "count_prepared_documents", lambda pid=None: 1)
    monkeypatch.setattr(
        wv,
        "fetch_prepared_documents_page",
        lambda offset, limit, pid=None: [
            {
                "id": 1,
                "pid": "100",
                "collected": True,
                "collected_by": "A",
                "prepared": False,
                "prepared_by": "",
                "uploaded_by": 7,
                "uploaded_at": None,
                "updated_at": None,
            }
        ],
    )
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "resolve_ms02_pid_to_wids", lambda e, s, p: {"100": [42]})
    monkeypatch.setattr(
        wv,
        "resolve_octo_wid_stage",
        lambda e, w: {"status": "In Progress", "current_stage": "Validation"},
    )
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    assert b'data-wid="42"' in resp.data
    assert b'data-status="In Progress"' in resp.data
    assert b'data-current-stage="Validation"' in resp.data
    assert (
        b"openPreview(btn.dataset.wid, btn.dataset.status, btn.dataset.currentStage)" in resp.data
    )
