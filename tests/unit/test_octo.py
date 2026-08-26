"""Unit tests for nx_lib.octo — Octopus runtime API client.

External HTTP and the IndexFieldMappings table aren't reachable in the
test environment; tests mock requests + the cache + engine_nexora_db.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
import requests

from nx_lib import octo as octo_mod
from nx_lib.octo import (
    get_access_token,
    get_activity_type_name,
    get_extensions_urls_fields,
    get_index_field_mappings,
    get_media,
    get_workitemdata_param,
    pdf_src_bytes,
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


def test_get_workitemdata_param_returns_none_on_http_error(app):
    """An Octo hiccup must return a falsy value, not raise -- callers guard
    with `if returndata:` expecting a "not found" signal, not an exception."""
    import requests as real_requests

    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(
            octo_mod.requests,
            "get",
            side_effect=real_requests.exceptions.ConnectionError("down"),
        ),
        app.app_context(),
    ):
        returndata = get_workitemdata_param("workitem-1", domain="octo.example")

    assert not returndata


def test_get_workitemdata_param_returns_none_on_bad_status(app):
    """A non-2xx response (e.g. Octo 404/500) must also be treated as a
    failure via raise_for_status, not blindly indexed for DocumentID."""
    import requests as real_requests

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = real_requests.exceptions.HTTPError("500 Server Error")

    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        app.app_context(),
    ):
        returndata = get_workitemdata_param("workitem-1", domain="octo.example")

    assert not returndata


def test_get_workitemdata_param_returns_none_on_missing_document_id(app):
    """A payload with no `DocumentID` key (e.g. `{}`) must return the same
    falsy sentinel as any other failure, not raise KeyError past the
    request-only except clause and kill callers like the activity feed."""
    fake_resp = MagicMock()
    fake_resp.json.return_value = {}

    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        app.app_context(),
    ):
        returndata = get_workitemdata_param("workitem-1", domain="octo.example")

    assert not returndata


# ---------- get_index_field_mappings ----------


def test_get_index_field_mappings_returns_dict_on_success(app, monkeypatch):
    monkeypatch.setattr(
        octo_mod.mapping_config,
        "field_aliases",
        lambda: {"Invoice_Date": "invoice_date", "Supplier_Name": "supplier"},
    )

    with app.app_context():
        mappings = get_index_field_mappings()

    assert mappings == {"Invoice_Date": "invoice_date", "Supplier_Name": "supplier"}


def test_get_index_field_mappings_returns_empty_on_db_error(app, monkeypatch):
    # mapping_config.field_aliases() itself degrades to {} on a registry
    # load failure (never caches the failure -- see mapping_config.registry());
    # get_index_field_mappings is a thin pass-through onto that contract.
    monkeypatch.setattr(octo_mod.mapping_config, "field_aliases", lambda: {})

    with app.app_context():
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
            # Dotted hosts are already FQDNs, so _media_url_for_gateway leaves them
            # unchanged (no-dot hosts get rewritten to the gateway -- that swap is
            # covered by test_octo_media.py); these tests assert parsing, not the swap.
            {"Url": "https://cdn.sydoc.ch/x.png", "Extension": ".PNG"},
            {"Url": "https://cdn.sydoc.ch/y.bin", "Extension": ".bin"},  # not in whitelist
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
    assert urls == ["https://cdn.sydoc.ch/x.png"]
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
                "Media": [{"Url": "https://cdn.sydoc.ch/a.jpg", "Extension": ".jpg"}],
                "IndexFields": [],
            },
            {
                "Media": [{"Url": "https://cdn.sydoc.ch/b.tif", "Extension": ".TIF"}],
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
    assert urls == ["https://cdn.sydoc.ch/a.jpg", "https://cdn.sydoc.ch/b.tif"]
    assert fields == {}
    assert field_sources == []
    assert table_sources == []


def test_get_extensions_urls_fields_non_batch_container_recurses(app):
    """MS02-style nested document (MobScnBatch -> MobScnDossier ->
    MobScnDocument): images + mapped fields aggregate from the leaf documents,
    even though no DocumentType is the literal 'Batch'."""
    leaf1 = {
        "DocumentType": "MobScnDocument",
        "Media": [{"Url": "https://cdn.sydoc.ch/p1.jpg", "Extension": ".jpg"}],
        "IndexFields": [{"Name": "DokArtName", "FieldValue": {"Text": "Bewilligungen"}}],
    }
    leaf2 = {
        "DocumentType": "MobScnDocument",
        "Media": [{"Url": "https://cdn.sydoc.ch/p2.jpg", "Extension": ".jpg"}],
        "IndexFields": [{"Name": "DokDatum", "FieldValue": {"Text": "2026-06-17"}}],
    }
    dossier = {
        "DocumentType": "MobScnDossier",
        "Media": [],
        "IndexFields": [],
        "ChildDocuments": [leaf1, leaf2],
    }
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "DocumentType": "MobScnBatch",
        "Media": [],
        "IndexFields": [],
        "ChildDocuments": [dossier],
    }
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        patch.object(
            octo_mod,
            "get_index_field_mappings",
            return_value={"DokArtName": "doc_type", "DokDatum": "doc_date"},
        ),
        app.app_context(),
    ):
        extensions, urls, fields, field_sources, table_sources = get_extensions_urls_fields(
            "wid", "doc-ms02"
        )

    assert extensions == [".jpg", ".jpg"]
    assert urls == ["https://cdn.sydoc.ch/p1.jpg", "https://cdn.sydoc.ch/p2.jpg"]
    assert fields == {"doc_type": "Bewilligungen", "doc_date": "2026-06-17"}
    assert field_sources == [
        {"key": "doc_type", "label": "doc_type", "value": "Bewilligungen", "locations": []},
        {"key": "doc_date", "label": "doc_date", "value": "2026-06-17", "locations": []},
    ]


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


def test_get_extensions_urls_fields_pdf_pages_offset_later_field(app):
    """Mixed PDF + image container: child0 is a PDF (expands to N pages via
    real I/O), child1 is an image with a mapped field. The field's page must
    account for child0's expanded PDF pages, not silently treat the PDF as 0
    pages (the bug: 'Show sources' highlighted the wrong page for later
    leaves in a mixed PDF+image container)."""
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "DocumentType": "Batch",
        "ChildDocuments": [
            {
                "Media": [{"Url": "https://cdn.sydoc.ch/a.pdf", "Extension": ".pdf"}],
                "IndexFields": [],
            },
            {
                "Media": [{"Url": "https://cdn.sydoc.ch/b.jpg", "Extension": ".jpg"}],
                "IndexFields": [
                    {
                        "Name": "Invoice_Date",
                        "FieldValue": {"Text": "2026-06-01"},
                        "Location": {
                            "PageIndex": 0,
                            "Rectangle": {
                                "Left": 1,
                                "Top": 1,
                                "Width": 5,
                                "Height": 5,
                            },
                        },
                    }
                ],
            },
        ],
    }
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        patch.object(
            octo_mod, "get_index_field_mappings", return_value={"Invoice_Date": "invoice_date"}
        ),
        patch.object(octo_mod, "pdf_src_bytes", return_value=b"%PDF-fake"),
        patch.object(octo_mod, "pdf_page_count", return_value=3),
        app.app_context(),
    ):
        extensions, urls, fields, field_sources, table_sources = get_extensions_urls_fields(
            "wid", "doc-mixed"
        )

    # 3 PDF page slots + 1 image slot
    assert extensions == [".pdf", ".pdf", ".pdf", ".jpg"]
    assert len(urls) == 4
    # The field lives on child1 (page index 0 locally) -> global page 3, after
    # the 3 PDF page slots contributed by child0.
    assert field_sources == [
        {
            "key": "invoice_date",
            "label": "invoice_date",
            "value": "2026-06-01",
            "locations": [{"page": 3, "rect": {"left": 1, "top": 1, "width": 5, "height": 5}}],
        }
    ]


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


def test_get_media_raises_on_http_error(app):
    """A 502/error body must not be handed back as if it were valid media
    bytes -- get_media has to check the response status so a transient Octo
    outage can't be mistaken for a real document."""
    fake_resp = MagicMock(content=b"<html>502 Bad Gateway</html>")
    fake_resp.raise_for_status.side_effect = requests.HTTPError("502 Server Error")
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        app.app_context(),
        pytest.raises(requests.HTTPError),
    ):
        get_media("https://cdn/x.png")


def test_pdf_src_bytes_does_not_cache_on_http_error(app):
    """pdf_src_bytes caches get_media's result for an hour -- if get_media
    raises instead of silently returning an error body, the cache.set below
    it must never execute, so a transient 502 doesn't poison the slot for
    every request in the next 3600s."""
    from nx_lib.extensions import cache

    url = "https://cdn/doc.pdf"
    key = "pdf_src_" + hashlib.sha1(url.encode("utf-8")).hexdigest()

    fake_resp = MagicMock(content=b"<html>502 Bad Gateway</html>")
    fake_resp.raise_for_status.side_effect = requests.HTTPError("502 Server Error")
    with (
        patch.object(octo_mod, "get_access_token", return_value="tok"),
        patch.object(octo_mod.requests, "get", return_value=fake_resp),
        app.app_context(),
        pytest.raises(requests.HTTPError),
    ):
        pdf_src_bytes(url)

    with app.app_context():
        assert cache.get(key) is None, (
            "pdf_src_bytes cached an error response -- the next request for this "
            "PDF will be served garbage bytes for up to an hour"
        )


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
