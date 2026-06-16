"""Unit tests for nx_lib.octo — Octopus runtime API client.

External HTTP and the IndexFieldMappings table aren't reachable in the
test environment; tests mock requests + the cache + engine_nexora_db.
"""

from unittest.mock import MagicMock, patch

import pytest

from nx_lib import octo as octo_mod
from nx_lib.octo import (
    get_access_token,
    get_activity_type_name,
    get_extensions_urls_fields,
    get_index_field_mappings,
    get_media,
    get_workitemdata_param,
)


@pytest.fixture(autouse=True)
def clear_cache(app):
    """Flush Flask-Caching between tests so cached tokens / mappings
    don't leak between cases."""
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()
    yield
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()


# ---------- get_access_token ----------


def test_get_access_token_returns_token_on_success(app):
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {"access_token": "abc123", "expires_in": 3600}
    with (
        patch.object(octo_mod.requests, "post", return_value=fake_resp) as mock_post,
        app.app_context(),
    ):
        tok = get_access_token(domain="octo.example")
    assert tok == "abc123"
    mock_post.assert_called_once()
    # URL contains the domain
    assert "octo.example" in mock_post.call_args.kwargs["url"]


def test_get_access_token_uses_default_domain(app):
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {"access_token": "x", "expires_in": 100}
    with (
        patch.object(octo_mod.requests, "post", return_value=fake_resp),
        app.app_context(),
    ):
        tok = get_access_token()
    assert tok == "x"


def test_get_access_token_uses_cached_token(app):
    """A second call within timeout returns the same cached token without HTTP."""
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {"access_token": "cached-tok", "expires_in": 3600}
    with (
        patch.object(octo_mod.requests, "post", return_value=fake_resp) as mock_post,
        app.app_context(),
    ):
        tok1 = get_access_token(domain="cache.example")
        tok2 = get_access_token(domain="cache.example")
    assert tok1 == tok2 == "cached-tok"
    assert mock_post.call_count == 1  # second call hit cache


def test_get_access_token_returns_none_on_http_error(app):
    import requests as real_requests

    with (
        patch.object(
            octo_mod.requests,
            "post",
            side_effect=real_requests.exceptions.ConnectTimeout("timeout"),
        ),
        app.app_context(),
    ):
        tok = get_access_token(domain="bad.example")
    assert tok is None


def test_get_access_token_uses_per_client_creds(app, monkeypatch):
    """A registered non-default domain signs the token request with that
    client's client_id/secret, not the global default creds."""
    from nx_lib import clients

    monkeypatch.setattr(
        clients,
        "octo_creds_for_domain",
        lambda domain: ("MS02_ID", "MS02_SECRET", "client_credentials")
        if domain == "ms02.octo.example"
        else ("DEF_ID", "DEF_SECRET", "client_credentials"),
    )
    # Re-point the name octo.py imported, too (it imported the function object).
    monkeypatch.setattr(octo_mod, "octo_creds_for_domain", clients.octo_creds_for_domain)

    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {"access_token": "ms02-tok", "expires_in": 3600}
    with (
        patch.object(octo_mod.requests, "post", return_value=fake_resp) as mock_post,
        app.app_context(),
    ):
        tok = get_access_token(domain="ms02.octo.example")

    assert tok == "ms02-tok"
    sent_body = mock_post.call_args.kwargs["data"]
    assert sent_body["client_id"] == "MS02_ID"
    assert sent_body["client_secret"] == "MS02_SECRET"


# ---------- get_workitemdata_param ----------


def test_get_workitemdata_param_returns_base64_and_doc_id(app):
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"DocumentID": "doc-42", "Other": "value"}

    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        app.app_context(),
    ):
        b64, doc_id = get_workitemdata_param("workitem-1", domain="octo.example")

    import base64

    decoded = base64.b64decode(b64).decode("utf-8")
    import json as _json

    assert _json.loads(decoded) == {"DocumentID": "doc-42", "Other": "value"}
    assert doc_id == "doc-42"


# ---------- get_index_field_mappings ----------


def test_get_index_field_mappings_returns_dict_on_success(app):
    fake_cursor = MagicMock()
    # Rows have row.SourceFieldName / row.TargetKey attrs
    row_a = MagicMock(SourceFieldName="Invoice_Date", TargetKey="invoice_date")
    row_b = MagicMock(SourceFieldName="Supplier_Name", TargetKey="supplier")
    fake_cursor.fetchall.return_value = [row_a, row_b]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with (
        patch.object(octo_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.return_value = fake_conn
        mappings = get_index_field_mappings()

    assert mappings == {"Invoice_Date": "invoice_date", "Supplier_Name": "supplier"}


def test_get_index_field_mappings_returns_empty_on_db_error(app):
    with (
        patch.object(octo_mod, "engine_nexora_db") as mock_engine,
        app.app_context(),
    ):
        mock_engine.raw_connection.side_effect = RuntimeError("DB down")
        mappings = get_index_field_mappings()
    assert mappings == {}


# ---------- get_extensions_urls_fields ----------


def test_get_extensions_urls_fields_single_doc(app):
    """Non-batch document: parse a single media list + index fields."""
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "DocumentType": "Single",
        "Media": [
            {"Url": "https://cdn/x.png", "Extension": ".PNG"},
            {"Url": "https://cdn/y.bin", "Extension": ".bin"},  # not in whitelist
        ],
        "IndexFields": [
            {"Name": "Invoice_Date", "FieldValue": {"Text": "2026-06-01"}},
            {"Name": "Unknown_Field", "FieldValue": {"Text": "ignored"}},
        ],
    }

    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        patch.object(
            octo_mod,
            "get_index_field_mappings",
            return_value={"Invoice_Date": "invoice_date"},
        ),
        app.app_context(),
    ):
        extensions, urls, fields, field_sources, table_sources = get_extensions_urls_fields(
            "wid", "doc-1"
        )

    assert extensions == [".png"]
    assert urls == ["https://cdn/x.png"]
    assert fields == {"invoice_date": "2026-06-01"}
    # mapped field with a value but no Location -> present, un-locatable
    assert field_sources == [
        {"key": "invoice_date", "label": "invoice_date", "value": "2026-06-01", "locations": []}
    ]
    # with_tables defaults False -> no table payload for the scalar-only callers
    assert table_sources == []


def test_get_extensions_urls_fields_batch_doc_iterates_children(app):
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "DocumentType": "Batch",
        "ChildDocuments": [
            {
                "Media": [{"Url": "https://cdn/a.jpg", "Extension": ".jpg"}],
                "IndexFields": [],
            },
            {
                "Media": [{"Url": "https://cdn/b.tif", "Extension": ".TIF"}],
                "IndexFields": [],
            },
        ],
    }
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        patch.object(octo_mod, "get_index_field_mappings", return_value={}),
        app.app_context(),
    ):
        extensions, urls, fields, field_sources, table_sources = get_extensions_urls_fields(
            "wid", "doc-batch"
        )
    assert extensions == [".jpg", ".tif"]
    assert urls == ["https://cdn/a.jpg", "https://cdn/b.tif"]
    assert fields == {}
    assert field_sources == []
    assert table_sources == []


def test_get_extensions_urls_fields_returns_empties_on_http_error(app):
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(
            octo_mod.requests,
            "get",
            side_effect=RuntimeError("network down"),
        ),
        app.app_context(),
    ):
        extensions, urls, fields, field_sources, table_sources = get_extensions_urls_fields(
            "wid", "doc"
        )
    assert extensions == []
    assert urls == []
    assert fields == {}
    assert field_sources == []
    assert table_sources == []


def test_get_extensions_urls_fields_with_tables_parses_tables(app):
    """with_tables=True requests WithTables=true and returns parsed table_sources."""
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "DocumentType": "Single",
        "Media": [{"Url": "https://cdn/p.jpg", "Extension": ".jpg"}],
        "IndexFields": [],
        "Tables": [
            {
                "Name": "TabVat",
                "Rows": [
                    {
                        "Cells": [
                            {
                                "ColumnName": "TabNetAmount",
                                "CellValue": {"Text": "236.82"},
                                "Confidence": 0.0,
                                "Location": {
                                    "PageIndex": 0,
                                    "Rectangle": {
                                        "Left": 851,
                                        "Top": 2407,
                                        "Width": 543,
                                        "Height": 544,
                                    },
                                },
                            }
                        ]
                    }
                ],
            }
        ],
    }
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp) as mock_get,
        patch.object(octo_mod, "get_index_field_mappings", return_value={}),
        app.app_context(),
    ):
        *_rest, table_sources = get_extensions_urls_fields("wid", "doc-t", with_tables=True)

    assert "WithTables=true" in mock_get.call_args.kwargs["url"]
    assert len(table_sources) == 1
    assert table_sources[0]["title"] == "TabVat"
    cell = table_sources[0]["rows"][0][0]
    assert cell["value"] == "236.82"
    assert cell["locations"][0]["page"] == 0


# ---------- get_media ----------


def test_get_media_returns_bytes(app):
    fake_resp = MagicMock(content=b"\x89PNG\r\n binary blob")
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp) as mock_get,
        app.app_context(),
    ):
        body = get_media("https://cdn/x.png")
    assert body.startswith(b"\x89PNG")
    # Auth header was attached
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok"


# ---------- get_activity_type_name ----------


def test_get_activity_type_name_returns_name_on_success(app):
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {"ActivityTypeName": "Review"}
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        app.app_context(),
    ):
        name = get_activity_type_name("inst-1")
    assert name == "Review"


def test_get_activity_type_name_returns_unknown_when_field_missing(app):
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {}
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        app.app_context(),
    ):
        name = get_activity_type_name("inst-2")
    assert name == "Unknown Activity"


def test_get_activity_type_name_returns_error_translation_on_http_failure(app):
    """The error path goes through Flask-Babel's gettext which needs a
    request context (locale resolution reads session)."""
    import requests as real_requests

    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(
            octo_mod.requests,
            "get",
            side_effect=real_requests.exceptions.ConnectionError("down"),
        ),
        app.test_request_context("/"),
    ):
        name = get_activity_type_name("inst-3")
    assert "Error" in name or "error" in name
