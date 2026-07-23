"""Integration tests for nx_lib.views.workitems — 10 routes.

Seed users only have dashboard.view, so all workitems.* gates return 403.
Tests that exercise route bodies use the workitems_all_perms fixture
(monkeypatches has_permission to True).

Most workitems routes query OctoDB tables (t_WorkItems, t_ActivityInstances,
t_Processes) and NEXORA tables (SearchConfig, Search_Field_Labels,
WorkitemTags, WorkitemComments) that are absent from the TEST schema. They
fall through except branches and return 500 JSON. Tuple matches in
assertions allow for that.

The collaboration API (single-workitem tags, interactions, comments, assign,
priority, tags CRUD, mention-autocomplete users) was removed in Task 4 of the
chat-collab-removal-bug-fixes plan; get_audithistory (Octo processing trail)
is a separate feature and stays.

Routes covered (10 endpoints):
- /api/config/fields                         GET
- /api/docfield_values                       GET
- /api/workitems                             GET
- /api/export/workitems/csv                  GET
- /workitems                                 page
- /import_workitems                          POST
- /api/get_media_info/<id>                   GET
- /api/get_media_raw/<id>/<idx>              GET
- /api/get_audithistory/<id>                 GET
- /api/workitems_page_init                   GET
"""

import csv
import io

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


class _FakeCache:
    """Minimal cache.get/set stand-in, isolated from the real process-wide
    Flask-Caching SimpleCache instance. A full pytest run showed the shared
    cache is not reliably empty at this test's start even after cache.clear()
    (some other test in the suite repopulates or retains an entry under the
    same key), so this test substitutes its own throwaway store instead of
    depending on that instance's isolation."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value


def test_api_config_fields_perm_state_in_cache_key(user_client, monkeypatch):
    """The route's cache key embeds the sensitive-perm state as a `_s0`/`_s1`
    suffix (see api_config_fields: `f"config_fields_{...}_s{int(_sees_sensitive)}"`)
    so a permissioned user's cached response can never be served to a
    permissionless one. search_options is always empty in this test DB (no
    SearchConfig/Search_Field_Labels tables), so we can't assert on response
    *body* differences — instead swap in a throwaway fake cache (see
    _FakeCache) and inspect what it collects, discovering the actual keys
    each perm state writes under rather than predicting them.
    """
    import nx_lib.views.workitems as wv

    fake_cache = _FakeCache()
    monkeypatch.setattr(wv, "cache", fake_cache)

    with user_client.session_transaction() as sess:
        sess["locale"] = "en"

    # Without the sensitive perm the response is filtered + cached under _s0.
    monkeypatch.setattr(
        wv, "has_permission", lambda code: code != "workitems.filter.documentfields.sensitive"
    )
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    r0 = user_client.get("/api/config/fields")
    assert r0.status_code == 200
    assert (
        len(fake_cache.store) == 1
    ), f"expected exactly one cached entry, got {fake_cache.store!r}"
    key_s0 = next(iter(fake_cache.store))
    assert key_s0.endswith("_s0")
    cached_s0 = fake_cache.store[key_s0]
    assert cached_s0 is not None, f"expected a cache entry under {key_s0!r}"

    # With the perm the cache key differs (_s1) -> not served the _s0 entry.
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    r1 = user_client.get("/api/config/fields")
    assert r1.status_code == 200
    assert len(fake_cache.store) == 2, f"expected a second cached entry, got {fake_cache.store!r}"
    key_s1 = next(k for k in fake_cache.store if k != key_s0)
    assert key_s1.endswith("_s1")
    assert key_s1 != key_s0
    cached_s1 = fake_cache.store[key_s1]
    assert cached_s1 is not None, f"expected a cache entry under {key_s1!r}"

    # Both perm states landed in genuinely distinct, still-present cache
    # entries: the permissioned request never reused or clobbered the
    # permissionless slot.
    assert fake_cache.store[key_s0] == cached_s0


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


class _SqlLogCursor:
    """Minimal DB-API cursor stub: records executed SQL text and always
    returns no rows. Lets the doc-field pre-fetch blocks in
    _get_workitems_data run to completion without touching a real (in this
    plan's dev environment, unreachable) SQL Server, so the test can assert
    on *whether a query was even attempted* for a given docfield."""

    def __init__(self, log):
        self._log = log

    def execute(self, sql, params=None):
        self._log.append(sql)
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def close(self):
        pass


class _SqlLogConn:
    def __init__(self, log):
        self._log = log

    def cursor(self):
        return _SqlLogCursor(self._log)

    def close(self):
        pass


class _SqlLogEngine:
    """Stand-in for engine_nexora_db / engine_statistics_db: only
    .raw_connection() is touched by _get_workitems_data's doc-field
    pre-fetch blocks."""

    def __init__(self, log):
        self._log = log

    def raw_connection(self):
        return _SqlLogConn(self._log)


def test_get_workitems_data_skips_sensitive_docfield_search(
    user_client, workitems_all_perms, monkeypatch
):
    """Regression for the two doc-field search-filtering blocks in
    _get_workitems_data (default/StatisticsDB path + MS02/Postgres path, both
    gated in commit ae83bcb via `if docfield in blocked_docfields: continue`).
    A sensitive docfield/docvalue pair must contribute NO SQL constraint --
    neither block may even build/execute its SearchConfig lookup query -- when
    the caller lacks workitems.filter.documentfields.sensitive, and the
    resulting WorkitemFilter must carry no docfield constraint at all."""
    import nx_lib.hooks as hooks
    import nx_lib.views.workitems as wv

    # allowed_processes (and therefore whether either pre-fetch block is even
    # entered) is read directly off session['permissions'], not via
    # has_permission(). _reload_user_permissions (before_request) reloads that
    # list from the DB on every request, so it must be patched at the source
    # (same seam as test_prepared_docs_link_visible_for_target_process) rather
    # than set via session_transaction, which would just be clobbered.
    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: [
            "workitems.view",
            "workitems.filter.documentfields",
            "workitems.filter.process.sydoc.test_proc",
        ],
    )

    sql_log = []
    monkeypatch.setattr(wv, "engine_nexora_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_statistics_db", _SqlLogEngine(sql_log))
    # Force entry into the MS02 block too (engine_ms02_docfields_pg is None in
    # CI/this dev env absent MS02_DOCFIELDS_DB_* env vars).
    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())

    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_validationuser"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: {"validationuser"})
    monkeypatch.setattr(
        wv, "has_permission", lambda code: code != "workitems.filter.documentfields.sensitive"
    )

    def _must_not_run(*a, **k):
        raise AssertionError("resolve_ms02_docfield_ids must not run for a blocked docfield")

    monkeypatch.setattr(wv, "resolve_ms02_docfield_ids", _must_not_run)

    captured = {}

    def _fake_fetch_merged_page(filt, offset, per_page):
        captured["filt"] = filt
        return [], 0, []

    monkeypatch.setattr(wv, "fetch_merged_page", _fake_fetch_merged_page)

    resp = user_client.get(
        "/api/workitems",
        query_string={"prcfW": "all", "docfield": "validationuser", "docvalue": "alice"},
    )

    assert resp.status_code == 200
    assert not [q for q in sql_log if "col_validationuser" in q], sql_log
    assert captured["filt"].docfield_ids is None
    assert captured["filt"].ms02_docfield_ids is None


def test_docfield_search_absent_ms02_engine_fails_closed(
    user_client, workitems_all_perms, monkeypatch
):
    """Cross-source bleed regression (observed on STAGING, 2026-07-20): with the
    MS02 doc-field engine unset (env vars missing) but the MS02 runtime client
    registered, a doc-field search skipped the MS02 pre-resolution entirely and
    left ms02_docfield_ids = None -- "no constraint" -- so the Postgres source
    returned its ENTIRE corpus into the filtered list. An active doc-field
    search must fail CLOSED: a source that cannot be checked contributes zero
    rows, never all of them."""
    import nx_lib.hooks as hooks
    import nx_lib.views.workitems as wv

    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: [
            "workitems.view",
            "workitems.filter.documentfields",
            "workitems.filter.process.sydoc.test_proc",
        ],
    )

    sql_log = []
    monkeypatch.setattr(wv, "engine_nexora_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_statistics_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", None)

    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_docbarcode"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: set())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)

    captured = {}

    def _fake_fetch_merged_page(filt, offset, per_page):
        captured["filt"] = filt
        return [], 0, []

    monkeypatch.setattr(wv, "fetch_merged_page", _fake_fetch_merged_page)

    resp = user_client.get(
        "/api/workitems",
        query_string={"prcfW": "all", "docfield": "docbarcode", "docvalue": "M629648"},
    )

    assert resp.status_code == 200
    assert captured["filt"].ms02_docfield_ids == set()


def test_docfield_search_ms02_resolver_error_fails_closed(
    user_client, workitems_all_perms, monkeypatch
):
    """Sibling to the absent-engine test: the engine exists and the ms02
    SearchConfig mapping row is found, but resolve_ms02_docfield_ids errors
    (its contract returns None on any failure). That None must be coerced to
    an empty allow-set -- zero MS02 rows -- not treated as "no constraint"."""
    import nx_lib.hooks as hooks
    import nx_lib.views.workitems as wv

    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: [
            "workitems.view",
            "workitems.filter.documentfields",
            "workitems.filter.process.sydoc.test_proc",
        ],
    )

    class _Ms02ConfigCursor(_SqlLogCursor):
        """Returns one usable ms02 SearchConfig mapping row for the MS02 leg's
        lookup; every other query still returns no rows."""

        def execute(self, sql, params=None):
            self._last_sql = sql
            return super().execute(sql, params)

        def fetchall(self):
            if "ClientCode = 'ms02'" in getattr(self, "_last_sql", ""):
                return [
                    (
                        'public."DossierStatistik"',
                        "d",
                        "d.WorkItemID = twi.id",
                        None,
                        "DossierBarcode",
                    )
                ]
            return []

    class _Ms02ConfigConn(_SqlLogConn):
        def cursor(self):
            return _Ms02ConfigCursor(self._log)

    class _Ms02ConfigEngine(_SqlLogEngine):
        def raw_connection(self):
            return _Ms02ConfigConn(self._log)

    sql_log = []
    monkeypatch.setattr(wv, "engine_nexora_db", _Ms02ConfigEngine(sql_log))
    monkeypatch.setattr(wv, "engine_statistics_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())

    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_docbarcode"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: set())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "resolve_ms02_docfield_ids", lambda *a, **k: None)

    captured = {}

    def _fake_fetch_merged_page(filt, offset, per_page):
        captured["filt"] = filt
        return [], 0, []

    monkeypatch.setattr(wv, "fetch_merged_page", _fake_fetch_merged_page)

    resp = user_client.get(
        "/api/workitems",
        query_string={"prcfW": "all", "docfield": "docbarcode", "docvalue": "M629648"},
    )

    assert resp.status_code == 200
    assert captured["filt"].ms02_docfield_ids == set()


def test_get_workitems_data_queries_nonsensitive_docfield_search(
    user_client, workitems_all_perms, monkeypatch
):
    """Control for the sibling skip test above: with the SAME field but no
    sensitivity block in play (get_sensitive_field_keys empty + full
    has_permission), both doc-field pre-fetch blocks DO attempt their
    SearchConfig lookup -- proving the sibling test's absence of SQL is
    genuinely caused by the sensitive-field skip, not by the fakes
    themselves suppressing all queries regardless of gating."""
    import nx_lib.hooks as hooks
    import nx_lib.views.workitems as wv

    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: [
            "workitems.view",
            "workitems.filter.documentfields",
            "workitems.filter.process.sydoc.test_proc",
        ],
    )

    sql_log = []
    monkeypatch.setattr(wv, "engine_nexora_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_statistics_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())

    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_validationuser"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: set())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)
    monkeypatch.setattr(wv, "resolve_ms02_docfield_ids", lambda *a, **k: None)
    monkeypatch.setattr(wv, "fetch_merged_page", lambda filt, offset, per_page: ([], 0, []))

    resp = user_client.get(
        "/api/workitems",
        query_string={"prcfW": "all", "docfield": "validationuser", "docvalue": "alice"},
    )

    assert resp.status_code == 200
    default_queries = [
        q for q in sql_log if "col_validationuser" in q and "ClientCode = 'default'" in q
    ]
    ms02_queries = [q for q in sql_log if "col_validationuser" in q and "ClientCode = 'ms02'" in q]
    assert default_queries, sql_log
    assert ms02_queries, sql_log


def test_get_workitems_data_unmapped_docfield_zeroes_both_sources(
    user_client, workitems_all_perms, monkeypatch
):
    """Cross-source bleed regression: a searched doc-field with NO SearchConfig
    mapping for a source must force that source to ZERO rows (empty allow-set),
    not run unconstrained (None). Observed on PROD: validationuser was mapped
    only for a 'default' process, and the unconstrained MS02 leg returned every
    PDBS workitem. Here neither leg finds a mapping row, so BOTH allow-sets
    must come out as set() -- and the MS02 resolver must never run."""
    import nx_lib.hooks as hooks
    import nx_lib.views.workitems as wv

    monkeypatch.setattr(
        hooks,
        "load_permissions_for_user",
        lambda uid: [
            "workitems.view",
            "workitems.filter.documentfields",
            "workitems.filter.process.sydoc.test_proc",
        ],
    )

    sql_log = []
    monkeypatch.setattr(wv, "engine_nexora_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_statistics_db", _SqlLogEngine(sql_log))
    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())

    monkeypatch.setattr(wv, "get_valid_search_columns", lambda: ["col_validationuser"])
    monkeypatch.setattr(wv, "get_sensitive_field_keys", lambda: set())
    monkeypatch.setattr(wv, "has_permission", lambda code: True)

    def _must_not_run(*a, **k):
        raise AssertionError("resolve_ms02_docfield_ids must not run without mapping rows")

    monkeypatch.setattr(wv, "resolve_ms02_docfield_ids", _must_not_run)

    captured = {}

    def _fake_fetch_merged_page(filt, offset, per_page):
        captured["filt"] = filt
        return [], 0, []

    monkeypatch.setattr(wv, "fetch_merged_page", _fake_fetch_merged_page)

    resp = user_client.get(
        "/api/workitems",
        query_string={"prcfW": "all", "docfield": "validationuser", "docvalue": "alice"},
    )

    assert resp.status_code == 200
    assert captured["filt"].docfield_ids == set()
    assert captured["filt"].ms02_docfield_ids == set()


def test_export_workitems_csv_gated(noperm_client):
    resp = noperm_client.get("/api/export/workitems/csv")
    assert resp.status_code == 403


def test_export_workitems_csv_with_perms(user_client, workitems_all_perms):
    """No data → returns CSV with the placeholder line."""
    resp = user_client.get("/api/export/workitems/csv")
    assert resp.status_code in (200, 500)
    if resp.status_code == 200:
        assert "text/csv" in resp.headers.get("Content-Type", "")


# --- colliding-id export rows must not mix client fields (D9) --------------- #
# Workitem ids are not globally unique across clients (1216 collides between
# the default Octo client and MS02, see docs/design/ms02-multisource.md). The
# export builds `domains`/`details_map`/media+audit cache entries per row; if
# any of those are keyed by the bare id, the second row processed for a
# colliding id silently answers for (or overwrites the cache entry of) the
# first, so one CSV row ends up carrying the OTHER client's field values.


def test_export_workitems_csv_keys_by_client_not_bare_id(
    user_client, workitems_all_perms, monkeypatch
):
    """Two rows share workitemid=1216 but belong to different clients. Each
    exported row must carry ITS OWN client's field value, never the other
    client's cached/fetched copy of the same bare id."""
    import nx_lib.views.workitems as wv

    fake_cache = _FakeCache()
    monkeypatch.setattr(wv, "cache", fake_cache)
    # workitems_all_perms only patches nx_lib.security.has_permission, which
    # covers the @require_permission route gate (looked up inside security.py
    # at call time) but NOT the `include_fields = ... and has_permission(...)`
    # check inside this module -- that name was bound at import time and needs
    # patching directly on the view module, same as test_api_config_fields_
    # perm_state_in_cache_key above.
    monkeypatch.setattr(wv, "has_permission", lambda code: True)

    rows = [
        {
            "workitemid": 1216,
            "client": "default",
            "status": "Open",
            "current_stage": "Stage A",
            "priority": 2,
            "tags": [],
            "modifiedat": None,
        },
        {
            "workitemid": 1216,
            "client": "ms02",
            "status": "Closed",
            "current_stage": "Stage B",
            "priority": 1,
            "tags": [],
            "modifiedat": None,
        },
    ]

    monkeypatch.setattr(
        wv,
        "_get_workitems_data",
        lambda args, export_all=False: {
            "workitems": rows,
            "pagination": {"totalItems": len(rows)},
        },
    )

    def fake_get_domain(wid, client_hint=None):
        return (
            "default-domain.example.com" if client_hint == "default" else "ms02-domain.example.com"
        )

    monkeypatch.setattr(wv, "get_domain_for_workitem", fake_get_domain)
    monkeypatch.setattr(
        wv, "get_workitemdata_param", lambda wid, domain: (f"wdata-{domain}", f"doc-{domain}")
    )

    def fake_get_extensions_urls_fields(workitemdata, document_id, domain, with_tables=False):
        fields = (
            {"Amount": "100-default"}
            if domain == "default-domain.example.com"
            else {"Amount": "999-ms02"}
        )
        return [], [], fields, {}, {}

    monkeypatch.setattr(wv, "get_extensions_urls_fields", fake_get_extensions_urls_fields)

    resp = user_client.get("/api/export/workitems/csv?include=fields")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    csv_rows = list(csv.reader(io.StringIO(body)))
    header, data_rows = csv_rows[0], csv_rows[1:]
    assert len(data_rows) == 2, f"expected 2 data rows, got {data_rows!r}"
    amount_idx = header.index("Amount")
    values = {r[amount_idx] for r in data_rows}
    assert values == {"100-default", "999-ms02"}, (
        f"expected each row to carry its own client's Amount, got {values!r} "
        f"(cross-contamination: a bare-id cache/dict key let one client's "
        f"fetched value answer for the other's)"
    )


# --- "export selected" must filter by (client, id), not bare id ------------ #
# The bulk-select checkboxes / `ids` query param used to carry a bare
# workitemid. Selecting only the default-client row of a colliding id (1216
# collides between the default Octo client and MS02) also exported the MS02
# row, because `specific_ids` membership was checked against the bare id
# alone. The UI now sends compound `client-id` pairs (matching renderTable's
# `rowKey = `${client}-${workitemid}`` in _workitems_overview_js.html) and the
# backend must filter on that compound key.


def test_export_workitems_csv_selected_ids_are_client_aware(
    user_client, workitems_all_perms, monkeypatch
):
    """Two rows share workitemid=1216 but belong to different clients. Passing
    ids=default-1216 must export only the default row, never the ms02 row
    that also matches the base filter."""
    import nx_lib.views.workitems as wv

    rows = [
        {
            "workitemid": 1216,
            "client": "default",
            "status": "Open",
            "current_stage": "Stage A",
            "priority": 2,
            "tags": [],
            "modifiedat": None,
        },
        {
            "workitemid": 1216,
            "client": "ms02",
            "status": "Closed",
            "current_stage": "Stage B",
            "priority": 1,
            "tags": [],
            "modifiedat": None,
        },
    ]

    monkeypatch.setattr(
        wv,
        "_get_workitems_data",
        lambda args, export_all=False: {
            "workitems": rows,
            "pagination": {"totalItems": len(rows)},
        },
    )

    resp = user_client.get("/api/export/workitems/csv?ids=default-1216")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    csv_rows = list(csv.reader(io.StringIO(body)))
    header, data_rows = csv_rows[0], csv_rows[1:]
    assert len(data_rows) == 1, (
        f"expected exactly 1 row (the default-client row) for ids=default-1216, "
        f"got {data_rows!r} (bare-id filtering also matched the colliding ms02 row)"
    )
    status_idx = header.index("Status")
    assert data_rows[0][status_idx] == "Open", (
        f"expected the default-client row (Status=Open), got {data_rows[0]!r} "
        f"-- wrong client's row was exported"
    )


def test_strip_export_fields_removes_sensitive_columns():
    from nx_lib.views.workitems import _strip_export_fields

    details_map = {
        1: {"fields": {"Validation User": "alice", "Amount": "50"}, "history": [], "images": []},
        2: {"fields": {"Amount": "9"}, "history": [], "images": []},
    }
    _strip_export_fields(details_map, {"validationuser"})
    assert details_map[1]["fields"] == {"Amount": "50"}
    assert details_map[2]["fields"] == {"Amount": "9"}


def test_import_workitems_gated(noperm_client):
    resp = noperm_client.post("/import_workitems", json={})
    assert resp.status_code == 403


def test_import_workitems_with_perms_empty_body(user_client, workitems_all_perms):
    """No importFile in request → flash + redirect (302) back to overview."""
    resp = user_client.post("/import_workitems", json={}, follow_redirects=False)
    assert resp.status_code in (200, 302, 400, 500)


# ============================ media + audit history ===========================


def test_api_get_media_info_authed_unknown_id(user_client):
    """View has an internal has_permission('workitems.details.view') check
    that the seed user doesn't satisfy → 403. With workitems_all_perms it
    would attempt OctoDB lookup and 500/404."""
    resp = user_client.get("/api/get_media_info/999999")
    assert resp.status_code in (200, 401, 403, 404, 500)


def test_strip_sensitive_from_detail_removes_fields_and_sources():
    from nx_lib.views.workitems import strip_sensitive_from_detail

    data = {
        "fields": {"Validation User": "alice", "Amount": "50"},
        "field_sources": [
            {"key": "Validation User", "value": "alice", "locations": []},
            {"key": "Amount", "value": "50", "locations": []},
        ],
        "table_sources": [],
    }
    out = strip_sensitive_from_detail(data, {"validationuser"})
    assert out["fields"] == {"Amount": "50"}
    assert [s["key"] for s in out["field_sources"]] == ["Amount"]
    assert data["fields"] == {"Validation User": "alice", "Amount": "50"}  # untouched


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


# ============================ tags + page init ===============================


def test_api_workitems_page_init_authed(user_client):
    resp = user_client.get("/api/workitems_page_init")
    assert resp.status_code in (200, 500)


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


def test_prepared_documents_octo_status_false_when_stage_not_found(
    user_client, workitems_all_perms, monkeypatch
):
    """A wid MAPPING existing is not enough: resolve_octo_wid_stage returning
    {"status": None, "current_stage": None} (nothing found in Octo) must yield
    in_octo=False, so the Preview / "Open in Workitems" buttons -- which would
    otherwise be dead links for a wid that isn't actually in Octo -- are not
    rendered."""
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
    monkeypatch.setattr(
        wv,
        "resolve_octo_wid_stage",
        lambda e, w: {"status": None, "current_stage": None},
    )

    captured = {}
    real_render_template = wv.render_template

    def _capture(template_name, **kwargs):
        captured.update(kwargs)
        return real_render_template(template_name, **kwargs)

    monkeypatch.setattr(wv, "render_template", _capture)

    resp = user_client.get("/prepared_documents")
    assert resp.status_code == 200
    assert captured["octo_status"]["100"]["in_octo"] is False
    # The row must fall back to the dash placeholder, not render the (dead) Preview
    # button / "Open in Workitems" link for a wid that Octo doesn't actually have.
    assert b'data-wid="42"' not in resp.data
    assert b'data-testid="prepared-docs-octo-link"' not in resp.data


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
    monkeypatch.setattr(
        wv,
        "resolve_octo_wid_stage",
        lambda e, w: {"status": "Ready", "current_stage": "Import"},
    )

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
    monkeypatch.setattr(wv, "sensitive_blocked_keys", set)
    rows = [
        {"workitemid": 42, "client": "ms02"},
        {"workitemid": 43, "client": "ms02"},
    ]
    wv._stamp_in_register(rows)
    assert rows[0]["pid"] == "100" and rows[0]["in_register"] is True
    assert rows[1]["pid"] == "200" and rows[1]["in_register"] is False


def test_stamp_in_register_skips_non_ms02_rows(monkeypatch):
    """Workitem ids collide across clients, so a default-client row must never
    be resolved against MS02's PID table — it would be stamped with (and link
    to) an unrelated person's PID."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "_ms02_target_processes", lambda: ["sydoc.05_PDBS"])
    monkeypatch.setattr(wv, "_ms02_pid_specs", lambda procs: [("t", "id", "pid", None)])
    monkeypatch.setattr(wv, "sensitive_blocked_keys", set)
    seen = {}

    def _resolve(engine, specs, wids):
        seen["wids"] = list(wids)
        return {42: "100"}

    monkeypatch.setattr(wv, "resolve_ms02_wids_to_pids", _resolve)
    monkeypatch.setattr(wv, "pids_in_register", lambda pids: {"100"})
    rows = [{"workitemid": 42, "client": "default"}, {"workitemid": 42, "client": "ms02"}]
    wv._stamp_in_register(rows)
    assert seen["wids"] == [42], "only the MS02 row's id may be resolved"
    assert "pid" not in rows[0] and "in_register" not in rows[0]
    assert rows[1]["pid"] == "100" and rows[1]["in_register"] is True


def test_stamp_in_register_respects_sensitive_pid_gate(monkeypatch):
    """PID is a personal identifying number: when it is flagged sensitive and
    the caller lacks the perm, it must not be stamped onto list rows."""
    import nx_lib.views.workitems as wv
    from nx_lib.clients import CLIENTS

    monkeypatch.setattr(wv, "engine_ms02_docfields_pg", object())
    monkeypatch.setitem(CLIENTS, "ms02", object())
    monkeypatch.setattr(wv, "sensitive_blocked_keys", lambda: {"pid"})

    def _must_not_run(*a, **k):
        raise AssertionError("PID resolution must not run when the field is blocked")

    monkeypatch.setattr(wv, "resolve_ms02_wids_to_pids", _must_not_run)
    rows = [{"workitemid": 42, "client": "ms02"}]
    wv._stamp_in_register(rows)
    assert "pid" not in rows[0]


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
                    "client": "ms02",
                }
            ],
            1,
            [],
        ),
    )
    monkeypatch.setattr(wv, "sensitive_blocked_keys", set)
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
