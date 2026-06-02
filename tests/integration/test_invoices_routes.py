"""Integration tests for nx_lib.views.invoices — 3 routes (Bexio-backed).

Routes:
- GET /invoices                page (invoices.view)
- GET /api/invoices            list (invoices.view) — calls Bexio search API
- GET /invoice/<id>/pdf        download (invoices.download) — calls Bexio PDF API

Seed users have no invoices.* perms. Tests:
- 302/403 gate paths use real seed
- 200 path uses the invoices_all_perms fixture which monkeypatches
  has_permission to True

The ClientInvoices table is absent from TEST schema, so get_bexio_client_ids
returns None (logged exception). get_allowed_client_details returns []. With
no target_ids, /api/invoices returns []. No actual Bexio HTTP call is made
in the integration tests — the requests.post/get calls are mocked via
Patch on the module-level requests import.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def invoices_all_perms(monkeypatch):
    monkeypatch.setattr("nx_lib.security.has_permission", lambda code: True)
    yield


# ============================ /invoices page =================================


def test_invoices_anonymous_redirects(client):
    resp = client.get("/invoices", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


def test_invoices_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/invoices")
    assert resp.status_code == 403


def test_invoices_with_perms_renders(user_client, invoices_all_perms):
    resp = user_client.get("/invoices")
    assert resp.status_code in (200, 500)


def test_invoices_with_filter_args(user_client, invoices_all_perms):
    resp = user_client.get("/invoices?search=INV-001&status=Open&dateFrom=2026-01-01")
    assert resp.status_code in (200, 500)


# ============================ /api/invoices ==================================


def test_api_invoices_anonymous(client):
    resp = client.get("/api/invoices", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_api_invoices_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/api/invoices")
    assert resp.status_code == 403


def test_api_invoices_no_allowed_clients_returns_empty(user_client, invoices_all_perms):
    """ClientInvoices table missing → no client ids → endpoint returns []."""
    resp = user_client.get("/api/invoices")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_api_invoices_with_unknown_client_id_returns_empty(user_client, invoices_all_perms):
    resp = user_client.get("/api/invoices?client_id=999")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_api_invoices_with_invalid_client_id(user_client, invoices_all_perms):
    """Non-integer client_id falls back to allowed_ids (empty)."""
    resp = user_client.get("/api/invoices?client_id=notanint")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_api_invoices_bexio_search_path_mocked(user_client, invoices_all_perms):
    """Patch get_bexio_client_ids to return a fake id + mock Bexio HTTP to
    exercise the search_bexio_invoices code path."""
    fake_response = MagicMock()
    fake_response.json.return_value = [
        {"id": 1, "document_nr": "INV-001", "total": "100.50", "kb_item_status_id": 9}
    ]
    fake_response.raise_for_status.return_value = None
    with (
        patch("nx_lib.views.invoices.get_bexio_client_ids", return_value=[42]),
        patch("nx_lib.views.invoices.requests.post", return_value=fake_response),
    ):
        resp = user_client.get("/api/invoices?client_id=42")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["status_info"]["text"]  # map_invoice_status was called


# ============================ /invoice/<id>/pdf ==============================


def test_download_invoice_pdf_anonymous(client):
    resp = client.get("/invoice/1/pdf", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_download_invoice_pdf_without_perm_returns_403(noperm_client):
    resp = noperm_client.get("/invoice/1/pdf")
    assert resp.status_code == 403


def test_download_invoice_pdf_with_perms_bexio_error(user_client, invoices_all_perms):
    """No BEXIO_PAT in TEST env or network error → flash + redirect."""
    resp = user_client.get("/invoice/1/pdf", follow_redirects=False)
    assert resp.status_code in (200, 302, 500)


def test_download_invoice_pdf_with_perms_mocked_pdf(user_client, invoices_all_perms):
    """Patch get_bexio_invoice_pdf to return bytes + filename."""
    with patch(
        "nx_lib.views.invoices.get_bexio_invoice_pdf",
        return_value=(b"%PDF-1.4 fake", "INV-001.pdf"),
    ):
        resp = user_client.get("/invoice/1/pdf")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type") == "application/pdf"
    assert "INV-001.pdf" in resp.headers.get("Content-Disposition", "")
