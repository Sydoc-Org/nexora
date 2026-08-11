"""Integration tests for the reporting metrics registry (semantic layer Slice 1).

Covers the metrics-admin page + CRUD (gated reporting.semantic.admin), the
builder-facing metrics API, and the metric resolution path through
/api/reporting/run. TestAdmin holds every permission (seed), so admin_client
exercises the admin/CRUD routes against the real TEST DB; the run-path tests
stub _prepare_run's collaborators so they don't need a live Statistics DB.
"""

from unittest.mock import patch

# --- /reporting/metrics admin page -----------------------------------------


def test_metrics_admin_page_without_perm_403(user_client):
    assert user_client.get("/reporting/metrics").status_code == 403
    assert user_client.get("/api/reporting/admin/metrics").status_code == 403


def test_metrics_admin_page_renders(admin_client):
    resp = admin_client.get("/reporting/metrics")
    assert resp.status_code == 200
    assert b"reporting-metrics-admin" in resp.data


def test_metrics_admin_list_has_rows_and_sources(admin_client):
    data = admin_client.get("/api/reporting/admin/metrics").get_json()
    assert isinstance(data["rows"], list)
    # The source dropdown is fed from the effective sources (always has docprocessing).
    assert any(s["id"] == "docprocessing" for s in data["sources"])


# --- Metrics CRUD (against the real TEST DB, like the sources CRUD test) ----


def test_metrics_crud(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "crud_metric",
            "sourceId": "docprocessing",
            "label": "CRUD Metric",
            "aggregation": "count",
            "enabled": True,
            "sortOrder": 50,
        },
    )
    assert create.status_code == 200, create.data
    mid = create.get_json()["id"]
    try:
        rows = admin_client.get("/api/reporting/admin/metrics").get_json()["rows"]
        assert any(r["id"] == mid and r["label"] == "CRUD Metric" for r in rows)
        upd = admin_client.put(
            f"/api/reporting/admin/metrics/{mid}",
            json={
                "code": "crud_metric",
                "sourceId": "docprocessing",
                "label": "Renamed",
                "aggregation": "sum",
                "baseField": "Amount",
                "enabled": False,
                "sortOrder": 50,
            },
        )
        assert upd.status_code == 200
        rows = admin_client.get("/api/reporting/admin/metrics").get_json()["rows"]
        row = next(r for r in rows if r["id"] == mid)
        assert row["label"] == "Renamed"
        assert row["aggregation"] == "sum"
        assert row["baseField"] == "Amount"
        assert row["enabled"] is False
    finally:
        dele = admin_client.delete(f"/api/reporting/admin/metrics/{mid}")
        assert dele.status_code == 200
    assert admin_client.delete(f"/api/reporting/admin/metrics/{mid}").status_code == 404


def test_metrics_validation_400(admin_client):
    # bad code (must start with a letter/underscore)
    assert (
        admin_client.post(
            "/api/reporting/admin/metrics",
            json={
                "code": "1bad",
                "sourceId": "docprocessing",
                "label": "L",
                "aggregation": "count",
            },
        ).status_code
        == 400
    )
    # sum without a baseField
    assert (
        admin_client.post(
            "/api/reporting/admin/metrics",
            json={
                "code": "no_base",
                "sourceId": "docprocessing",
                "label": "L",
                "aggregation": "sum",
            },
        ).status_code
        == 400
    )
    # unknown aggregation
    assert (
        admin_client.post(
            "/api/reporting/admin/metrics",
            json={
                "code": "bad_agg",
                "sourceId": "docprocessing",
                "label": "L",
                "aggregation": "median",
                "baseField": "Amount",
            },
        ).status_code
        == 400
    )
    # missing sourceId
    assert (
        admin_client.post(
            "/api/reporting/admin/metrics",
            json={"code": "no_src", "label": "L", "aggregation": "count"},
        ).status_code
        == 400
    )


# --- Builder-facing /api/reporting/metrics ---------------------------------


def test_metrics_api_without_perm_403(user_client):
    assert user_client.get("/api/reporting/metrics").status_code == 403


def test_metrics_api_groups_by_accessible_source(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "api_doc_count",
            "sourceId": "docprocessing",
            "label": "Doc count",
            "aggregation": "count",
            "format": "int",
        },
    )
    mid = create.get_json()["id"]
    try:
        data = admin_client.get("/api/reporting/metrics").get_json()
        # TestAdmin holds reporting.source.docprocessing, so docprocessing metrics surface.
        assert "docprocessing" in data
        entry = next(m for m in data["docprocessing"] if m["code"] == "api_doc_count")
        assert entry["aggregation"] == "count"
        assert entry["format"] == "int"
    finally:
        admin_client.delete(f"/api/reporting/admin/metrics/{mid}")


def test_metrics_payload_carries_total_mode(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "api_total_mode_probe",
            "sourceId": "docprocessing",
            "label": "Total mode probe",
            "aggregation": "count",
            "format": "int",
        },
    )
    mid = create.get_json()["id"]
    try:
        resp = admin_client.get("/api/reporting/metrics")
        assert resp.status_code == 200
        items = [m for grp in resp.get_json().values() for m in grp]
        assert items and all("totalMode" in m for m in items)
    finally:
        admin_client.delete(f"/api/reporting/admin/metrics/{mid}")


# --- Metric resolution through /api/reporting/run --------------------------

_DOCPROC_SOURCE = {
    "id": "docprocessing",
    "kind": "curated",
    "label": "Document Processing",
    "permission": "reporting.source.docprocessing",
    "engine": "statistics",
    "provider": "docprocessing",
}

_RUN_DEF = {
    "schemaVersion": 1,
    "source": "docprocessing",
    "visualization": "table",
    "title": "By client",
    "columns": [{"field": "client"}],
    "filters": [],
    "sort": [],
    "scope": {},
    "rowLimit": 100,
    "metrics": [{"metric": "doc_count"}],
}

_CATALOG = [
    {"field": "client", "label": "Client", "filterable": True, "sortable": True},
]


def test_run_with_metric_returns_aggregated_rows(admin_client):
    with (
        patch("nx_lib.views.reporting._get_effective_source", return_value=_DOCPROC_SOURCE),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._metrics_for_source",
            return_value={"doc_count": {"aggregation": "count", "base_field": None}},
        ),
        patch("nx_lib.views.reporting.fetch_docprocessing_catalog", return_value=_CATALOG),
        patch("nx_lib.views.reporting._allowed_processes", return_value=["acme.invoice"]),
        patch("nx_lib.views.reporting._load_process_configs", return_value=[]),
        patch("nx_lib.views.reporting._load_field_col_maps", return_value={}),
        patch(
            "nx_lib.views.reporting.build_table_query",
            return_value=("SELECT [client], COUNT(*) AS [doc_count] FROM x GROUP BY [client]", []),
        ),
        patch("nx_lib.views.reporting._execute", return_value=[["Acme", 30]]),
    ):
        resp = admin_client.post("/api/reporting/run", json=_RUN_DEF)
    assert resp.status_code == 200, resp.data
    data = resp.get_json()
    fields = [c["field"] for c in data["columns"]]
    assert fields == ["client", "doc_count"]
    assert data["rows"] == [["Acme", 30]]
    assert data["rowCount"] == 1


def test_run_with_unknown_metric_returns_400(admin_client):
    bad = {**_RUN_DEF, "metrics": [{"metric": "ghost_metric"}]}
    with (
        patch("nx_lib.views.reporting._get_effective_source", return_value=_DOCPROC_SOURCE),
        patch("nx_lib.views.reporting.has_permission", return_value=True),
        patch(
            "nx_lib.views.reporting._metrics_for_source",
            return_value={"doc_count": {"aggregation": "count", "base_field": None}},
        ),
        patch("nx_lib.views.reporting.fetch_docprocessing_catalog", return_value=_CATALOG),
        patch("nx_lib.views.reporting._allowed_processes", return_value=["acme.invoice"]),
    ):
        resp = admin_client.post("/api/reporting/run", json=bad)
    # validate_report_definition rejects an unknown metric code (not in metric_codes).
    assert resp.status_code == 400


# --- Zero-dimension (grand total) metric runs -------------------------------


def test_run_zero_dim_metric_returns_single_total_row(admin_client):
    # Real-DB round trip over the generic table provider: register a table
    # source over the TEST Users table plus a count metric, then run a
    # zero-column definition and expect exactly one grand-total row with only
    # the metric column.
    create_src = admin_client.post(
        "/api/reporting/admin/sources",
        json={
            "code": "zd_users",
            "kind": "curated",
            "label": "ZeroDim Users",
            "permission": "reporting.source.docprocessing",
            "provider": "table",
            "engine": "nexora",
            "baseObject": "dbo.Users",
            "columns": [
                {
                    "field": "username",
                    "label": "Username",
                    "type": "string",
                    "filterable": True,
                    "sortable": True,
                },
            ],
            "enabled": True,
            "sortOrder": 10,
        },
    )
    assert create_src.status_code == 200, create_src.data
    sid = create_src.get_json()["id"]
    create_metric = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "zd_user_count",
            "sourceId": "zd_users",
            "label": "User count",
            "aggregation": "count",
            "format": "int",
        },
    )
    assert create_metric.status_code == 200, create_metric.data
    mid = create_metric.get_json()["id"]
    try:
        run = admin_client.post(
            "/api/reporting/run",
            json={
                "schemaVersion": 1,
                "source": "zd_users",
                "visualization": "table",
                "title": "Total users",
                "columns": [],
                "filters": [],
                "sort": [],
                "scope": {},
                "rowLimit": 100,
                "metrics": [{"metric": "zd_user_count"}],
            },
        )
        assert run.status_code == 200, run.data
        data = run.get_json()
        assert [c["field"] for c in data["columns"]] == ["zd_user_count"]
        assert data["rowCount"] == 1
        assert data["rows"][0][0] >= 1
    finally:
        admin_client.delete(f"/api/reporting/admin/metrics/{mid}")
        admin_client.delete(f"/api/reporting/admin/sources/{sid}")


def test_admin_metrics_roundtrip_localized_labels(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "api_l10n_metric",
            "sourceId": "docprocessing",
            "label": "Pages processed",
            "labelDe": "Verarbeitete Seiten",
            "labelFr": "Pages traitées",
            "aggregation": "sum",
            "baseField": "pagecount",
            "format": "int",
        },
    )
    assert create.status_code == 200
    mid = create.get_json()["id"]
    try:
        rows = admin_client.get("/api/reporting/admin/metrics").get_json()["rows"]
        row = next(r for r in rows if r["code"] == "api_l10n_metric")
        assert row["labelDe"] == "Verarbeitete Seiten"
        assert row["labelFr"] == "Pages traitées"
        assert row["labelIt"] is None
        upd = admin_client.put(
            f"/api/reporting/admin/metrics/{mid}",
            json={
                "code": "api_l10n_metric",
                "sourceId": "docprocessing",
                "label": "Pages processed",
                "labelDe": "Verarbeitete Seiten",
                "labelIt": "Pagine elaborate",
                "aggregation": "sum",
                "baseField": "pagecount",
            },
        )
        assert upd.status_code == 200
        rows = admin_client.get("/api/reporting/admin/metrics").get_json()["rows"]
        row = next(r for r in rows if r["code"] == "api_l10n_metric")
        assert row["labelIt"] == "Pagine elaborate"
        assert row["labelFr"] is None  # update replaces all three
    finally:
        admin_client.delete(f"/api/reporting/admin/metrics/{mid}")


def test_metrics_api_label_follows_session_locale_with_fallback(admin_client):
    create = admin_client.post(
        "/api/reporting/admin/metrics",
        json={
            "code": "api_l10n_pick",
            "sourceId": "docprocessing",
            "label": "Pages processed",
            "labelDe": "Verarbeitete Seiten",
            "aggregation": "sum",
            "baseField": "pagecount",
        },
    )
    assert create.status_code == 200
    mid = create.get_json()["id"]
    try:
        with admin_client.session_transaction() as sess:
            sess["locale"] = "de"
        data = admin_client.get("/api/reporting/metrics").get_json()
        entry = next(m for m in data["docprocessing"] if m["code"] == "api_l10n_pick")
        assert entry["label"] == "Verarbeitete Seiten"
        # No Italian translation -> falls back to the English Label.
        with admin_client.session_transaction() as sess:
            sess["locale"] = "it"
        data = admin_client.get("/api/reporting/metrics").get_json()
        entry = next(m for m in data["docprocessing"] if m["code"] == "api_l10n_pick")
        assert entry["label"] == "Pages processed"
    finally:
        with admin_client.session_transaction() as sess:
            sess["locale"] = "en"
        admin_client.delete(f"/api/reporting/admin/metrics/{mid}")
