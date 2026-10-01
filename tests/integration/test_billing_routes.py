"""Integration tests for nx_lib.views.billing -- Sydoc Billing (#436, was the
Finance Bexio panel of #423).

Routes covered:
- GET  /billing                                  the page (billing.view)
- GET  /api/billing/month                        the invoices of an invoice month
- GET  /api/billing/figures/<key>                Finance figures of the billed month
- GET  /api/billing/outstanding                  everything still owed
- GET  /api/billing/months                       the picker's month states
- GET  /api/billing/invoice/<id>                 one invoice with its lines
- GET  /api/billing/invoice/<id>/pdf             its PDF

Bexio itself is never called: the nx_lib.bexio network functions are stubbed,
so these tests pin the view's contract, the gates and how it reads the link
table (dbo.FinanceBexioContacts, mirrored in sql/test/schema.sql; migrations
set its rows, nothing in the app writes them).
"""

import calendar
import datetime as dt

import pytest

import nx_lib.views.billing as bv
from nx_lib import bexio, config
from nx_lib.db import engine_nexora_db

# The page's default month (the previous one) and the month it bills: derived
# from today, so the tests never fall out of the pickable range.
_t = dt.date.today()
_iy, _im = (_t.year, _t.month - 1) if _t.month > 1 else (_t.year - 1, 12)
_by, _bm = (_iy, _im - 1) if _im > 1 else (_iy - 1, 12)
MONTH = f"{_iy:04d}-{_im:02d}"
FIRST = f"{MONTH}-01"
LAST = f"{MONTH}-{calendar.monthrange(_iy, _im)[1]:02d}"
BILLED = f"{_by:04d}-{_bm:02d}"

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
    monkeypatch.setattr(
        bexio,
        "invoices",
        lambda ids, fresh=False: {
            i: {
                "id": i,
                "positions": [{"type": "KbPositionCustom", "text": "Pages", "amount": "20"}],
            }
            for i in ids
        },
    )
    monkeypatch.setattr(bexio, "latest_before", lambda ids, date_from, fresh=False: None)
    monkeypatch.setattr(bexio, "currencies", lambda fresh=False: {1: "CHF"})
    monkeypatch.setattr(
        bexio, "contact_names", lambda ids, fresh=False: {CONTACT: "Test Contact AG"}
    )
    return calls


def _sql(statement, *params):
    conn = engine_nexora_db.raw_connection()
    try:
        conn.cursor().execute(statement, params)
        conn.commit()
    finally:
        conn.close()


def link(client):
    """Link the test contact the way a migration does: straight into the table."""
    _sql("DELETE FROM dbo.FinanceBexioContacts WHERE ContactId = ?", CONTACT)
    _sql(
        "INSERT INTO dbo.FinanceBexioContacts (ContactId, Client, LinkedBy) VALUES (?, ?, 'test')",
        CONTACT,
        client,
    )


@pytest.fixture()
def clean_links():
    """The route reads through its own connection, so setup and cleanup commit
    (the transaction-scoped db_conn fixture would roll back -- or block)."""
    purge = "DELETE FROM dbo.FinanceBexioContacts WHERE ContactId = ?"
    _sql(purge, CONTACT)
    yield
    _sql(purge, CONTACT)


# ---- gates -----------------------------------------------------------------


def test_page_anonymous_redirects_to_login(client):
    resp = client.get("/billing", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")


@pytest.mark.parametrize(
    "path",
    [
        "/billing",
        "/api/billing/month",
        "/api/billing/figures/frigemo",
        "/api/billing/outstanding",
        "/api/billing/months",
        "/api/billing/invoice/1",
        "/api/billing/invoice/1/pdf",
    ],
)
def test_reads_without_billing_view_are_403(noperm_client, path):
    assert noperm_client.get(path).status_code == 403


@pytest.mark.parametrize(
    "path", ["/api/finance/bexio", "/api/finance/bexio/link", "/api/billing/link"]
)
def test_links_cannot_be_changed_and_the_old_panel_is_gone(admin_client, path):
    assert admin_client.post(path, json={"client": "Frigemo", "contactId": 1}).status_code in (
        404,
        405,
    )


# ---- the panel -------------------------------------------------------------


def test_panel_says_not_configured_without_a_token(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", None)
    body = admin_client.get(f"/api/billing/month?month={MONTH}").get_json()
    assert body["configured"] is False
    assert body["window"]["from"] == FIRST
    assert body["billed"]["month"] == BILLED
    assert body["error"]


def test_month_lists_the_invoices_dated_in_it(admin_client, bexio_on, clean_links):
    body = admin_client.get(f"/api/billing/month?month={MONTH}").get_json()
    assert body["configured"] is True and "canLink" not in body
    assert bexio_on == [("search", FIRST, LAST, False)]
    assert body["window"]["to"] == LAST
    assert "Sydoc" not in [c["client"] for c in body["clients"]]
    assert all(c["state"] == "unlinked" for c in body["clients"])
    # The test contact is linked to no client: its invoice is listed apart,
    # outside every total.
    assert body["totals"] == [] and body["count"] == 0
    assert [o["nr"] for o in body["others"]] == ["RE-501"]
    assert body["others"][0]["contact"] == "Test Contact AG"
    assert body["others"][0]["bexioUrl"].endswith("/501")


def test_panel_refresh_bypasses_the_cache(admin_client, bexio_on, clean_links):
    admin_client.get(f"/api/billing/month?month={MONTH}&fresh=1")
    assert bexio_on[0][3] is True


def test_panel_survives_missing_contact_names(admin_client, bexio_on, clean_links, monkeypatch):
    def fail(ids, fresh=False):
        raise bexio.BexioError("x", status=400)

    monkeypatch.setattr(bexio, "contact_names", fail)
    link("Frigemo")
    body = admin_client.get(f"/api/billing/month?month={MONTH}").get_json()
    assert "error" not in body
    frigemo = next(c for c in body["clients"] if c["client"] == "Frigemo")
    assert frigemo["contacts"] == [{"id": CONTACT, "name": f"#{CONTACT}"}]


def test_panel_reports_a_bexio_failure_in_place(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")

    def fail(*a, **k):
        raise bexio.BexioError("Bexio rejected the access token.", status=401)

    monkeypatch.setattr(bexio, "search_invoices", fail)
    resp = admin_client.get(f"/api/billing/month?month={MONTH}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is True and body["error"]


# ---- links -----------------------------------------------------------------


def test_a_linked_contact_counts_for_its_client(admin_client, bexio_on, clean_links):
    link("Frigemo")
    body = admin_client.get(f"/api/billing/month?month={MONTH}").get_json()
    frigemo = next(c for c in body["clients"] if c["client"] == "Frigemo")
    assert frigemo["state"] == "invoiced"
    assert frigemo["contacts"] == [{"id": CONTACT, "name": "Test Contact AG"}]
    assert frigemo["key"] == "frigemo"
    assert body["totals"] == [{"currency": "CHF", "total": 1077.0, "excl": 1000.0, "count": 1}]
    assert body["others"] == []
    # Lines come inline, read for every client invoice.
    assert frigemo["invoices"][0]["positions"][0]["text"] == "Pages"

    # A contact belongs to one client: moving the row moves the invoice.
    link("Aveniq")
    body = admin_client.get(f"/api/billing/month?month={MONTH}").get_json()
    states = {c["client"]: c["state"] for c in body["clients"]}
    assert states["Aveniq"] == "invoiced" and states["Frigemo"] == "unlinked"


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
    body = admin_client.get("/api/billing/invoice/7").get_json()
    assert body["nr"] == "RE-7" and body["currency"] == "CHF"
    assert body["positions"][0]["amount"] == 20.0
    assert body["bexioUrl"].endswith("/7")


def test_invoice_not_found_is_404_and_other_failures_502(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")
    status = {"value": 404}

    def fail(invoice_id, fresh=False):
        raise bexio.BexioError("x", status=status["value"])

    monkeypatch.setattr(bexio, "invoice", fail)
    assert admin_client.get("/api/billing/invoice/7").status_code == 404
    status["value"] = 500
    assert admin_client.get("/api/billing/invoice/7").status_code == 502


def test_invoice_without_a_token_is_503(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", None)
    assert admin_client.get("/api/billing/invoice/7").status_code == 503
    assert admin_client.get("/api/billing/invoice/7/pdf").status_code == 503


def test_pdf_is_served_inline_and_never_cached(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")
    monkeypatch.setattr(bexio, "invoice_pdf", lambda invoice_id: (b"%PDF-1.7", 'RE "7".pdf'))
    resp = admin_client.get("/api/billing/invoice/7/pdf")
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
    assert admin_client.get("/api/billing/invoice/7/pdf").status_code == 502


def test_view_module_uses_the_bexio_module_it_stubs():
    """The stubs above patch nx_lib.bexio; the view must call through it."""
    assert bv.bexio is bexio


# ---- the page and the new reads (#436) ---------------------------------------


def test_page_renders_the_shells_and_the_sidebar_group(admin_client):
    resp = admin_client.get(f"/billing?month={MONTH}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-testid="billing-band"' in html
    assert 'id="bill-frigemo"' in html and 'id="bill-other"' in html and 'id="bill-open"' in html
    assert 'data-testid="header-nav-sydoc-billing"' in html
    assert "window.NX_BILLING" in html


def test_finance_no_longer_carries_the_bexio_panel(admin_client):
    html = admin_client.get(f"/finance?month={BILLED}").get_data(as_text=True)
    assert 'id="fin-bexio"' not in html and "finance_bexio.js" not in html


def test_a_missing_client_names_its_latest_invoice(
    admin_client, bexio_on, clean_links, monkeypatch
):
    link("Frigemo")
    monkeypatch.setattr(bexio, "search_invoices", lambda *a, **k: [])
    seen = []

    def latest(ids, date_from, fresh=False):
        seen.append((list(ids), date_from))
        return {
            "id": 9,
            "document_nr": "RE-9",
            "is_valid_from": "2026-08-05",
            "kb_item_status_id": 31,
        }

    monkeypatch.setattr(bexio, "latest_before", latest)
    body = admin_client.get(f"/api/billing/month?month={MONTH}").get_json()
    frigemo = next(c for c in body["clients"] if c["client"] == "Frigemo")
    assert frigemo["state"] == "missing"
    assert frigemo["last"] == {"nr": "RE-9", "date": "2026-08-05", "status": "unpaid"}
    assert seen == [([CONTACT], FIRST)]


def test_figures_of_an_unknown_section_are_404(admin_client):
    assert admin_client.get(f"/api/billing/figures/nope?month={MONTH}").status_code == 404


def test_figures_read_the_billed_month(admin_client, monkeypatch):
    calls = []

    def payload(section, year, month):
        calls.append((section.key, year, month))
        return {
            "key": section.key,
            "client": section.client,
            "title": None,
            "error": None,
            "blocks": [{"figures": [{"label": "Docs", "value": 7}]}],
        }

    monkeypatch.setattr(bv, "_section_payload", payload)
    monkeypatch.setattr(bv, "_closed_safe", lambda month: {})
    body = admin_client.get(f"/api/billing/figures/frigemo?month={MONTH}").get_json()
    assert calls == [("frigemo", _by, _bm)]
    assert body["month"] == BILLED and body["closed"] is False
    assert body["figures"] == [{"label": "Docs", "value": 7, "unit": None}]


def test_outstanding_lists_what_is_owed(admin_client, clean_links, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")
    monkeypatch.setattr(bexio, "currencies", lambda fresh=False: {1: "CHF"})
    monkeypatch.setattr(
        bexio, "contact_names", lambda ids, fresh=False: {CONTACT: "Test Contact AG"}
    )
    monkeypatch.setattr(
        bexio,
        "search_outstanding",
        lambda fresh=False: [
            {
                "id": 1,
                "document_nr": "RE-1",
                "contact_id": CONTACT,
                "kb_item_status_id": bexio.PENDING,
                "is_valid_from": "2020-01-01",
                "is_valid_to": "2020-01-31",
                "total": "100",
                "total_remaining_payments": "100",
                "currency_id": 1,
            },
        ],
    )
    body = admin_client.get("/api/billing/outstanding").get_json()
    assert body["configured"] is True
    [row] = body["invoices"]
    assert row["linked"] is False and row["contact"] == "Test Contact AG" and row["overdueDays"] > 0
    assert body["totals"][0]["currency"] == "CHF" and body["overdue"] == 1


def test_months_without_a_token_answer_no_states(admin_client, monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", None)
    body = admin_client.get("/api/billing/months?year=2026").get_json()
    assert body == {"year": 2026, "states": {}, "configured": False}
