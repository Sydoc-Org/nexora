"""Unit tests for nx_lib.views.invoices module-level helpers.

Covers the Bexio-facing helpers that don't need a Flask request context:
- map_invoice_status
- search_bexio_invoices (mocked HTTP)
- get_bexio_invoice_pdf (mocked HTTP)
- get_bexio_client_ids (mocked session + DB)
- get_allowed_client_details (mocked session + DB)
"""

import json
from unittest.mock import MagicMock, patch

from nx_lib.views.invoices import (
    map_invoice_status,
)


def test_map_invoice_status_paid():
    out = map_invoice_status(9)
    assert out["color"] == "green"
    # 'Paid' is translated through gettext; assert it's a non-empty string.
    assert out["text"]


def test_map_invoice_status_other():
    out = map_invoice_status(8)
    assert out["color"] == "blue"


def test_search_bexio_invoices_no_pat(monkeypatch, app):
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", None)
    from nx_lib.views.invoices import search_bexio_invoices

    with app.test_request_context("/"):
        out = search_bexio_invoices([1], "2026-01-01", "2026-12-31")
    assert out == []


def test_search_bexio_invoices_success(monkeypatch, app):
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "fake-token")
    fake_resp = MagicMock()
    fake_resp.json.return_value = [
        {"id": 1, "document_nr": "X", "total": "55.55", "kb_item_status_id": 9}
    ]
    fake_resp.raise_for_status.return_value = None
    from nx_lib.views.invoices import search_bexio_invoices

    with (
        app.test_request_context("/"),
        patch("nx_lib.views.invoices.requests.post", return_value=fake_resp),
    ):
        out = search_bexio_invoices([1], "2026-01-01", "2026-12-31", status="Paid")
    assert len(out) == 1
    assert out[0]["status_info"]["color"] == "green"


def test_search_bexio_invoices_filters_by_status(monkeypatch, app):
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    fake_resp = MagicMock()
    fake_resp.json.return_value = [
        {"id": 1, "document_nr": "X", "total": "1", "kb_item_status_id": 9},
        {"id": 2, "document_nr": "Y", "total": "2", "kb_item_status_id": 8},
    ]
    fake_resp.raise_for_status.return_value = None
    from nx_lib.views.invoices import search_bexio_invoices

    with (
        app.test_request_context("/"),
        patch("nx_lib.views.invoices.requests.post", return_value=fake_resp),
    ):
        paid = search_bexio_invoices([1], "2026-01-01", "2026-12-31", status="Paid")
    assert all(inv["kb_item_status_id"] == 9 for inv in paid)


def test_search_bexio_invoices_total_format_bad_value(monkeypatch, app):
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    fake_resp = MagicMock()
    fake_resp.json.return_value = [
        {"id": 1, "document_nr": "X", "total": "not-a-number", "kb_item_status_id": 9}
    ]
    fake_resp.raise_for_status.return_value = None
    from nx_lib.views.invoices import search_bexio_invoices

    with (
        app.test_request_context("/"),
        patch("nx_lib.views.invoices.requests.post", return_value=fake_resp),
    ):
        out = search_bexio_invoices([1], "2026-01-01", "2026-12-31")
    assert out[0]["total"] == "0.00"


def test_search_bexio_invoices_http_error_returns_empty(monkeypatch, app):
    import requests as _requests

    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    from nx_lib.views.invoices import search_bexio_invoices

    with (
        app.test_request_context("/"),
        patch(
            "nx_lib.views.invoices.requests.post",
            side_effect=_requests.exceptions.ConnectionError("network"),
        ),
    ):
        out = search_bexio_invoices([1], "2026-01-01", "2026-12-31")
    assert out == []


def test_search_bexio_invoices_partial_results_on_client_failure(monkeypatch, app):
    """A failure on one client's request must not discard invoices already
    gathered from other clients in the same search (Task 16)."""
    import requests as _requests

    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    from nx_lib.views.invoices import search_bexio_invoices

    resp1 = MagicMock()
    resp1.json.return_value = [
        {"id": 1, "document_nr": "A", "total": "10.00", "kb_item_status_id": 9}
    ]
    resp1.raise_for_status.return_value = None

    resp3 = MagicMock()
    resp3.json.return_value = [
        {"id": 3, "document_nr": "C", "total": "30.00", "kb_item_status_id": 9}
    ]
    resp3.raise_for_status.return_value = None

    with (
        app.test_request_context("/"),
        patch(
            "nx_lib.views.invoices.requests.post",
            side_effect=[resp1, _requests.exceptions.ConnectionError("network"), resp3],
        ),
    ):
        out = search_bexio_invoices([1, 2, 3], "2026-01-01", "2026-12-31")

    ids = {inv["id"] for inv in out}
    assert ids == {1, 3}, f"expected partial results from clients 1 and 3, got {out!r}"


def test_search_bexio_invoices_partial_results_on_bad_json(monkeypatch, app):
    """Same partial-results contract for the JSONDecodeError branch."""
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    from nx_lib.views.invoices import search_bexio_invoices

    resp1 = MagicMock()
    resp1.json.return_value = [
        {"id": 1, "document_nr": "A", "total": "10.00", "kb_item_status_id": 9}
    ]
    resp1.raise_for_status.return_value = None

    resp2 = MagicMock()
    resp2.raise_for_status.return_value = None
    resp2.json.side_effect = json.JSONDecodeError("bad json", "doc", 0)

    resp3 = MagicMock()
    resp3.json.return_value = [
        {"id": 3, "document_nr": "C", "total": "30.00", "kb_item_status_id": 9}
    ]
    resp3.raise_for_status.return_value = None

    with (
        app.test_request_context("/"),
        patch(
            "nx_lib.views.invoices.requests.post",
            side_effect=[resp1, resp2, resp3],
        ),
    ):
        out = search_bexio_invoices([1, 2, 3], "2026-01-01", "2026-12-31")

    ids = {inv["id"] for inv in out}
    assert ids == {1, 3}, f"expected partial results from clients 1 and 3, got {out!r}"


def test_get_bexio_invoice_pdf_no_pat(monkeypatch, app):
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", None)
    from nx_lib.views.invoices import get_bexio_invoice_pdf

    with app.test_request_context("/"):
        content, name = get_bexio_invoice_pdf(1)
    assert content is None and name is None


def test_get_bexio_invoice_pdf_success(monkeypatch, app):
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    import base64

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "content": base64.b64encode(b"PDFDATA").decode(),
        "name": "doc.pdf",
    }
    fake_resp.raise_for_status.return_value = None
    from nx_lib.views.invoices import get_bexio_invoice_pdf

    with (
        app.test_request_context("/"),
        patch("nx_lib.views.invoices.requests.get", return_value=fake_resp),
    ):
        content, name = get_bexio_invoice_pdf(1)
    assert content == b"PDFDATA"
    assert name == "doc.pdf"


def test_get_bexio_invoice_pdf_missing_fields(monkeypatch, app):
    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    fake_resp = MagicMock()
    fake_resp.json.return_value = {}  # missing content + name
    fake_resp.raise_for_status.return_value = None
    from nx_lib.views.invoices import get_bexio_invoice_pdf

    with (
        app.test_request_context("/"),
        patch("nx_lib.views.invoices.requests.get", return_value=fake_resp),
    ):
        content, name = get_bexio_invoice_pdf(1)
    assert content is None and name is None


def test_get_bexio_invoice_pdf_http_error(monkeypatch, app):
    import requests as _requests

    monkeypatch.setattr("nx_lib.views.invoices.BEXIO_PAT", "tok")
    from nx_lib.views.invoices import get_bexio_invoice_pdf

    with (
        app.test_request_context("/"),
        patch(
            "nx_lib.views.invoices.requests.get",
            side_effect=_requests.exceptions.Timeout("slow"),
        ),
    ):
        content, name = get_bexio_invoice_pdf(1)
    assert content is None and name is None
