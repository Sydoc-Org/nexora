"""Integration tests for nx_lib.views.finance_bexio -- the Bexio invoice panel (#423).

Routes covered:
- GET  /api/finance/bexio                        the panel for a month
- GET  /api/finance/bexio/invoice/<id>           one invoice with its lines
- GET  /api/finance/bexio/invoice/<id>/pdf       its PDF
- POST /api/finance/bexio/link|unlink            client <-> contact links

Bexio itself is never called: the nx_lib.bexio network functions are stubbed,
so these tests pin the view's contract, the gates and the link table
(dbo.FinanceBexioContacts, mirrored in sql/test/schema.sql).
"""

import pytest

import nx_lib.views.finance_bexio as fbv
from nx_lib import bexio, config
from nx_lib.db import engine_nexora_db

CONTACT = 910001  # far outside any real Bexio id, so cleanup cannot hit a real link


@pytest.fixture()
def bexio_on(monkeypatch):
    """A configured Bexio whose calls answer from memory."""
    calls = []
    monkeypatch.setattr(config, "BEXIO_PAT", "pat-for-tests")

    def search(date_from, date_to, fresh=False):
        calls.append(("search", date_from, date_to, fresh))
        return [
            {
                "id": 501,
                "document_nr": "RE-501",
                "title": "Scanning August",
                "contact_id": CONTACT,
                "kb_item_status_id": bexio.PENDING,
                "is_valid_from": "2026-09-03",
                "total": "1077.00",
                "total_taxes": "77.00",
                "currency_id": 1,
            }
        ]

    monkeypatch.setattr(bexio, "search_invoices", search)
    monkeypatch.setattr(bexio, "currencies", lambda fresh=False: {1: "CHF"})
    monkeypatch.setattr(
        bexio, "contact_names", lambda ids, fresh=False: {CONTACT: "Test Contact AG"}
    )
    return calls


@pytest.fixture()
def clean_links():
    """The routes commit through their own connections, so cleanup commits too
    (the transaction-scoped db_conn fixture would roll back -- or block)."""

    def purge():
        conn = engine_nexora_db.raw_connection()
        try:
            conn.cursor().execute(
                "DELETE FROM dbo.FinanceBexioContacts WHERE ContactId = ?", (CONTACT,)
            )
            conn.commit()
        finally:
            conn.close()

    purge()
    yield
    purge()


# ---- gates -----------------------------------------------------------------


def test_panel_anonymous_redirects_to_login(client):
    resp = client.get("/api/finance/bexio", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


@pytest.mark.parametrize(
    "path",
    ["/api/finance/bexio", "/api/finance/bexio/invoice/1", "/api/finance/bexio/invoice/1/pdf"],
)
def test_reads_without_finance_view_are_403(noperm_client, path):
    assert noperm_client.get(path).status_code == 403


@pytest.mark.parametrize("path", ["/api/finance/bexio/link", "/api/finance/bexio/unlink"])
def test_writes_without_month_edit_are_403(noperm_client, path):
    assert noperm_client.post(path, json={"client": "Frigemo", "contactId": 1}).status_code == 403


# ---- the panel -------------------------------------------------------------


def test_panel_says_not_configured_without_a_token(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", None)
    body = admin_client.get("/api/finance/bexio?month=2026-08").get_json()
    assert body["configured"] is False
    assert body["window"]["from"] == "2026-09-01"
    assert body["error"]


def test_panel_reconciles_the_following_month(admin_client, bexio_on, clean_links):
    body = admin_client.get("/api/finance/bexio?month=2026-08").get_json()
    assert body["configured"] is True and body["canLink"] is True
    assert bexio_on == [("search", "2026-09-01", "2026-09-30", False)]
    assert body["window"]["to"] == "2026-09-30"
    assert "Sydoc" not in [c["client"] for c in body["clients"]]
    assert all(c["state"] == "unlinked" for c in body["clients"])
    # The test contact is linked to no client, so its invoice is left out.
    assert body["totals"] == [] and body["count"] == 0


def test_panel_refresh_bypasses_the_cache(admin_client, bexio_on, clean_links):
    admin_client.get("/api/finance/bexio?month=2026-08&fresh=1")
    assert bexio_on[0][3] is True


def test_panel_survives_missing_contact_names(admin_client, bexio_on, clean_links, monkeypatch):
    def fail(ids, fresh=False):
        raise bexio.BexioError("x", status=400)

    monkeypatch.setattr(bexio, "contact_names", fail)
    admin_client.post("/api/finance/bexio/link", json={"client": "Frigemo", "contactId": CONTACT})
    body = admin_client.get("/api/finance/bexio?month=2026-08").get_json()
    assert "error" not in body
    frigemo = next(c for c in body["clients"] if c["client"] == "Frigemo")
    assert frigemo["contacts"] == [{"id": CONTACT, "name": f"#{CONTACT}"}]


def test_panel_reports_a_bexio_failure_in_place(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")

    def fail(*a, **k):
        raise bexio.BexioError("Bexio rejected the access token.", status=401)

    monkeypatch.setattr(bexio, "search_invoices", fail)
    resp = admin_client.get("/api/finance/bexio?month=2026-08")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is True and body["error"]
    assert body["canLink"] is False


# ---- linking ---------------------------------------------------------------


def test_link_assigns_a_contact_to_its_client(admin_client, bexio_on, clean_links):
    resp = admin_client.post(
        "/api/finance/bexio/link", json={"client": "Frigemo", "contactId": CONTACT}
    )
    assert resp.status_code == 200
    body = admin_client.get("/api/finance/bexio?month=2026-08").get_json()
    frigemo = next(c for c in body["clients"] if c["client"] == "Frigemo")
    assert frigemo["state"] == "invoiced"
    assert frigemo["contacts"] == [{"id": CONTACT, "name": "Test Contact AG"}]
    assert body["totals"] == [{"currency": "CHF", "total": 1077.0, "excl": 1000.0, "count": 1}]

    # Relinking moves it: a contact belongs to one client.
    admin_client.post("/api/finance/bexio/link", json={"client": "Aveniq", "contactId": CONTACT})
    body = admin_client.get("/api/finance/bexio?month=2026-08").get_json()
    states = {c["client"]: c["state"] for c in body["clients"]}
    assert states["Aveniq"] == "invoiced" and states["Frigemo"] == "unlinked"

    assert (
        admin_client.post("/api/finance/bexio/unlink", json={"contactId": CONTACT}).status_code
        == 200
    )
    assert (
        admin_client.post("/api/finance/bexio/unlink", json={"contactId": CONTACT}).status_code
        == 404
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"client": "Sydoc", "contactId": CONTACT},  # services name no client of their own
        {"client": "Nobody", "contactId": CONTACT},
        {"client": "Frigemo", "contactId": "x"},
        {"client": "Frigemo", "contactId": 0},
        {},
    ],
)
def test_link_rejects_unknown_clients_and_bad_ids(admin_client, payload):
    assert admin_client.post("/api/finance/bexio/link", json=payload).status_code == 400


def test_unlink_rejects_a_bad_id(admin_client):
    assert admin_client.post("/api/finance/bexio/unlink", json={}).status_code == 400


# ---- one invoice -----------------------------------------------------------


def test_invoice_lines(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")
    monkeypatch.setattr(bexio, "currencies", lambda fresh=False: {1: "CHF"})
    monkeypatch.setattr(
        bexio,
        "invoice",
        lambda invoice_id, fresh=False: {
            "id": invoice_id,
            "document_nr": "RE-7",
            "total": "10.00",
            "currency_id": 1,
            "positions": [
                {
                    "type": "KbPositionCustom",
                    "text": "Pages",
                    "amount": "20",
                    "unit_price": "0.5",
                    "position_total": "10",
                }
            ],
        },
    )
    body = admin_client.get("/api/finance/bexio/invoice/7").get_json()
    assert body["nr"] == "RE-7" and body["currency"] == "CHF"
    assert body["positions"][0]["amount"] == 20.0
    assert body["bexioUrl"].endswith("/7")


def test_invoice_not_found_is_404_and_other_failures_502(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")
    status = {"value": 404}

    def fail(invoice_id, fresh=False):
        raise bexio.BexioError("x", status=status["value"])

    monkeypatch.setattr(bexio, "invoice", fail)
    assert admin_client.get("/api/finance/bexio/invoice/7").status_code == 404
    status["value"] = 500
    assert admin_client.get("/api/finance/bexio/invoice/7").status_code == 502


def test_invoice_without_a_token_is_503(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", None)
    assert admin_client.get("/api/finance/bexio/invoice/7").status_code == 503
    assert admin_client.get("/api/finance/bexio/invoice/7/pdf").status_code == 503


def test_pdf_is_served_inline_and_never_cached(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")
    monkeypatch.setattr(bexio, "invoice_pdf", lambda invoice_id: (b"%PDF-1.7", 'RE "7".pdf'))
    resp = admin_client.get("/api/finance/bexio/invoice/7/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["Content-Disposition"] == 'inline; filename="RE 7.pdf"'
    assert resp.data == b"%PDF-1.7"


def test_pdf_failure_is_502(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")

    def fail(invoice_id):
        raise bexio.BexioError("x", status=500)

    monkeypatch.setattr(bexio, "invoice_pdf", fail)
    assert admin_client.get("/api/finance/bexio/invoice/7/pdf").status_code == 502


def test_view_module_uses_the_bexio_module_it_stubs():
    """The stubs above patch nx_lib.bexio; the view must call through it."""
    assert fbv.bexio is bexio
