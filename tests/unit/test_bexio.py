"""nx_lib.bexio: the read-only Bexio client behind Sydoc Billing (#423, #436).

The pure half (window, normalization, reconciliation) is tested on literal
payloads shaped like Bexio's. The network half runs against a stubbed
``requests.request`` -- no call ever leaves the machine, and every one is
checked to be a read (GET, or a search POST).
"""

import base64
from types import SimpleNamespace

import pytest
import requests

from nx_lib import bexio, config
from nx_lib.finance import billed_clients


@pytest.fixture(autouse=True)
def _fresh_cache():
    bexio.clear_cache()
    yield
    bexio.clear_cache()


class FakeResponse:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._body = body
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._body


@pytest.fixture()
def http(monkeypatch):
    """Stub requests.request; ``http.routes[(method, path)]`` answers, calls are recorded."""

    stub = SimpleNamespace(routes={}, calls=[])

    def request(method, url, headers=None, json=None, params=None, timeout=None):
        path = url.removeprefix(bexio.API)
        stub.calls.append(
            {
                "method": method,
                "path": path,
                "json": json,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        answer = stub.routes.get((method, path))
        if callable(answer):
            return answer(json=json, params=params)
        if answer is None:
            return FakeResponse(404)
        return answer

    monkeypatch.setattr(config, "BEXIO_PAT", "pat-for-tests")
    monkeypatch.setattr(bexio.requests, "request", request)
    return stub


def _raw(
    id_,
    contact,
    status=bexio.PENDING,
    total="1077.00",
    taxes="77.00",
    date="2026-09-05",
    nr=None,
    currency=1,
):
    return {
        "id": id_,
        "document_nr": nr or f"RE-{id_:05d}",
        "title": f"Invoice {id_}",
        "contact_id": contact,
        "kb_item_status_id": status,
        "is_valid_from": date,
        "is_valid_to": "2026-10-05",
        "total": total,
        "total_taxes": taxes,
        "currency_id": currency,
    }


# ---- configuration -----------------------------------------------------------


def test_unconfigured_means_no_network(monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", None)

    def boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("network touched without a token")

    monkeypatch.setattr(bexio.requests, "request", boom)
    assert bexio.configured() is False
    with pytest.raises(bexio.BexioError, match="not configured"):
        bexio.search_invoices("2026-09-01", "2026-09-30")


def test_configured_follows_the_token(monkeypatch):
    monkeypatch.setattr(config, "BEXIO_PAT", "x")
    assert bexio.configured() is True


# ---- the invoice window --------------------------------------------------------


@pytest.mark.parametrize(
    "year, month, expected",
    [
        (2026, 8, ("2026-09-01", "2026-09-30", (2026, 9))),
        (2026, 12, ("2027-01-01", "2027-01-31", (2027, 1))),
        (2028, 1, ("2028-02-01", "2028-02-29", (2028, 2))),  # leap year
    ],
)
def test_invoice_window_is_the_following_month(year, month, expected):
    assert bexio.invoice_window(year, month) == expected


def test_invoice_window_offset_zero_is_the_month_itself():
    assert bexio.invoice_window(2026, 8, offset=0) == ("2026-08-01", "2026-08-31", (2026, 8))


# ---- normalization ------------------------------------------------------------


def test_normalize_invoice_derives_excl_vat_and_maps_status():
    inv = bexio.normalize_invoice(_raw(12, 7, status=bexio.PAID), {1: "CHF"})
    assert inv == {
        "id": 12,
        "nr": "RE-00012",
        "title": "Invoice 12",
        "contactId": 7,
        "projectId": None,
        "date": "2026-09-05",
        "due": "2026-10-05",
        "status": "paid",
        "total": 1077.0,
        "excl": 1000.0,
        "vat": 77.0,
        "vatRate": None,
        "paid": 0.0,
        "open": 1077.0,  # no remaining-payments field: nothing is known paid
        "currency": "CHF",
        "currencyId": 1,
    }


def test_normalize_invoice_tolerates_missing_and_odd_values():
    inv = bexio.normalize_invoice(
        {"id": "3", "kb_item_status_id": 99, "total": "abc", "is_valid_from": "2026-09-01 00:00:00"}
    )
    assert inv["status"] == "other"
    assert inv["total"] == 0.0 and inv["excl"] == 0.0
    assert inv["date"] == "2026-09-01"
    assert inv["contactId"] is None and inv["currency"] == ""
    assert inv["projectId"] is None


def test_normalize_invoice_carries_the_bexio_project():
    assert bexio.normalize_invoice({**_raw(12, 7), "project_id": "10"})["projectId"] == 10


def test_normalize_positions_keeps_lines_text_subtotals_and_discounts():
    lines = bexio.normalize_positions(
        [
            {
                "type": "KbPositionCustom",
                "text": "<p>Scanning <strong>Opex</strong></p><p>August&nbsp;2026</p>",
                "amount": "1234.000000",
                "unit_name": "Stk",
                "unit_price": "0.450000",
                "discount_in_percent": "0.000000",
                "position_total": "555.300000",
            },
            {
                "type": "KbPositionArticle",
                "text": "Setup",
                "amount": "1",
                "unit_price": "100",
                "position_total": "90",
                "discount_in_percent": "10",
                "is_optional": True,
            },
            {"type": "KbPositionText", "text": "Details per branch attached."},
            {"type": "KbPositionText", "text": None},
            {"type": "KbPositionPagebreak"},
            {"type": "KbPositionSubtotal", "text": "Subtotal", "value": "645.30"},
            {"type": "KbPositionDiscount", "text": "Loyalty", "discount_total": "45.30"},
        ]
    )
    assert [line["kind"] for line in lines] == [
        "line",
        "line",
        "text",
        "text",
        "subtotal",
        "discount",
    ]
    assert lines[3]["text"] == ""
    assert lines[0]["text"] == "Scanning Opex\nAugust\xa02026"
    assert lines[0]["amount"] == 1234.0 and lines[0]["unitPrice"] == 0.45
    assert lines[0]["total"] == 555.3 and lines[0]["unit"] == "Stk"
    assert lines[1]["discount"] == 10.0 and lines[1]["optional"] is True
    assert lines[4]["total"] == 645.3
    assert lines[5]["total"] == -45.3


def test_normalize_positions_of_nothing_is_empty():
    assert bexio.normalize_positions(None) == []


# ---- reconciliation -----------------------------------------------------------


def _inv(id_, contact, status="open", total=100.0, excl=90.0, currency="CHF", date="2026-09-05"):
    return {
        "id": id_,
        "nr": f"RE-{id_}",
        "title": "",
        "contactId": contact,
        "date": date,
        "due": None,
        "status": status,
        "total": total,
        "excl": excl,
        "currency": currency,
    }


def test_reconcile_states_per_client():
    clients = ["Elektro-Material", "Compass Group", "Privera", "Frigemo"]
    links = [
        bexio.Link("Elektro-Material", 1),
        bexio.Link("Compass Group", 2),
        bexio.Link("Privera", 3),
        bexio.Link("Privera", 4),
    ]
    invoices = [
        _inv(10, 1),
        _inv(11, 2, status="draft"),
        _inv(12, 4, status="paid", total=50.0, excl=45.0),
        _inv(13, 3, status="cancelled", total=999.0, excl=999.0),
        _inv(14, 9),
    ]
    out = bexio.reconcile(clients, links, invoices, {1: "EM AG", 3: "Privera AG", 9: "Stranger"})
    states = {r["client"]: r["state"] for r in out["clients"]}
    assert states == {
        "Elektro-Material": bexio.INVOICED,
        "Compass Group": bexio.DRAFT_ONLY,
        "Privera": bexio.INVOICED,  # the paid one counts, the cancelled one does not
        "Frigemo": bexio.UNLINKED,
    }
    privera = out["clients"][2]
    assert [c["name"] for c in privera["contacts"]] == ["Privera AG", "#4"]
    assert privera["totals"] == [{"currency": "CHF", "total": 50.0, "excl": 45.0, "count": 1}]
    # Unlinked contact 9 is listed apart (others), outside every total; drafts
    # and cancelled invoices are listed but never counted as billed.
    assert [(o["nr"], o["contact"]) for o in out["others"]] == [("RE-14", "Stranger")]
    assert out["cancelled"] == 1
    assert out["totals"] == [{"currency": "CHF", "total": 150.0, "excl": 135.0, "count": 2}]
    assert out["count"] == 4
    assert out["drafts"] == 1


def test_reconcile_linked_without_invoice_is_missing():
    out = bexio.reconcile(["Frigemo"], [bexio.Link("Frigemo", 5)], [], {})
    assert out["clients"][0]["state"] == bexio.MISSING
    assert out["totals"] == [] and out["count"] == 0


def test_reconcile_ignores_links_to_clients_not_on_the_page():
    out = bexio.reconcile(["Frigemo"], [bexio.Link("Gone", 1)], [_inv(1, 1)], {})
    assert out["clients"][0]["state"] == bexio.UNLINKED
    assert out["totals"] == [] and out["count"] == 0


def test_reconcile_totals_split_by_currency():
    out = bexio.reconcile(
        ["Frigemo"], [bexio.Link("Frigemo", 1)], [_inv(1, 1, currency="EUR"), _inv(2, 1)], {}
    )
    assert [t["currency"] for t in out["totals"]] == ["CHF", "EUR"]


def test_billed_clients_are_distinct_and_exclude_sydoc_services():
    clients = billed_clients()
    assert len(clients) == len(set(clients))
    assert "Privera" in clients and "Sydoc" not in clients
    assert clients[0] == "Elektro-Material"


def test_normalize_invoice_reads_payments_and_the_vat_rate():
    raw = {
        **_raw(12, 7, status=bexio.PARTIAL),
        "total_received_payments": "400.00",
        "total_remaining_payments": "677.0000",
        "taxs": [{"percentage": "8.10", "value": "77.00"}],
    }
    inv = bexio.normalize_invoice(raw)
    assert (inv["paid"], inv["open"], inv["vat"], inv["vatRate"]) == (400.0, 677.0, 77.0, 8.1)
    two = {**raw, "taxs": [{"percentage": "8.10"}, {"percentage": "2.60"}]}
    assert bexio.normalize_invoice(two)["vatRate"] is None


# ---- outstanding ----------------------------------------------------------------


def _owed(id_, contact, due, open_=100.0, status="open", currency="CHF"):
    return {**_inv(id_, contact, status=status, currency=currency), "due": due, "open": open_}


def test_outstanding_sorts_by_due_and_counts_overdue_per_currency():
    invoices = [
        _owed(1, 1, "2026-10-20"),
        _owed(2, 9, "2026-08-14", open_=50.0, status="unpaid"),
        _owed(3, 1, "2026-09-30", open_=25.0, status="partial"),
        _owed(4, 1, "2026-09-01", open_=7.0, currency="EUR"),
        _inv(5, 1, status="paid"),  # not owed: dropped
    ]
    out = bexio.outstanding(
        invoices, [bexio.Link("Frigemo", 1)], ["Frigemo"], {9: "Stranger AG"}, "2026-10-01"
    )
    assert [r["id"] for r in out["invoices"]] == [2, 4, 3, 1]
    stranger = out["invoices"][0]
    assert stranger["linked"] is False and stranger["contact"] == "Stranger AG"
    assert stranger["overdueDays"] == 48
    assert out["invoices"][-1]["client"] == "Frigemo" and out["invoices"][-1]["overdueDays"] == 0
    # CHF first, nothing converted; an invoice due today is not overdue.
    assert out["totals"] == [
        {"currency": "CHF", "open": 175.0, "count": 3, "overdue": 75.0, "overdueCount": 2},
        {"currency": "EUR", "open": 7.0, "count": 1, "overdue": 7.0, "overdueCount": 1},
    ]
    assert out["overdue"] == 3


def test_outstanding_ignores_links_to_clients_not_on_the_page():
    out = bexio.outstanding(
        [_owed(1, 1, None)], [bexio.Link("Gone", 1)], ["Frigemo"], {}, "2026-10-01"
    )
    assert out["invoices"][0]["linked"] is False and out["invoices"][0]["overdueDays"] == 0


# ---- picker month states ----------------------------------------------------------


def test_month_states_per_invoice_month():
    links = [bexio.Link("Frigemo", 1), bexio.Link("Aveniq", 2), bexio.Link("Aveniq", 3)]
    invoices = [
        _inv(1, 1, date="2026-08-03"),
        _inv(2, 3, date="2026-08-04"),  # Aveniq's second contact counts for it
        _inv(3, 1, date="2026-09-03"),
        _inv(4, 2, date="2026-09-03", status="draft"),  # a draft is not invoiced
        _inv(5, 2, date="2026-10-01"),
    ]
    clients = ["Frigemo", "Aveniq", "Privera"]  # Privera has no link: not checked
    states = bexio.month_states(invoices, links, clients, 2026, "2026-10-01")
    assert states["2026-08"] == "all"
    assert states["2026-09"] == "missing:1"
    assert states["2026-01"] == "missing:2"
    assert states["2026-10"] == "running"
    assert "2026-11" not in states and len(states) == 10


# ---- network: the new reads ---------------------------------------------------------


def test_search_outstanding_filters_by_owed_status(http):
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, [_raw(1, 7)])
    assert [r["id"] for r in bexio.search_outstanding()] == [1]
    assert http.calls[-1]["json"] == [
        {"field": "kb_item_status_id", "value": ["8", "16", "31"], "criteria": "in"}
    ]


def test_latest_before_takes_the_latest_date_not_the_highest_id(http):
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(
        200, [_raw(9, 7, date="2026-07-01"), _raw(8, 7, date="2026-08-05"), _raw(7, 7, date=None)]
    )
    assert bexio.latest_before([7], "2026-09-01")["id"] == 8
    assert http.calls[-1]["params"]["order_by"] == "id_desc"
    assert bexio.latest_before([], "2026-09-01") is None


def test_invoices_reads_in_parallel_and_keeps_a_failure_per_invoice(monkeypatch):
    def one(invoice_id, fresh=False):
        if invoice_id == 2:
            raise bexio.BexioError("x", status=500)
        return {"id": invoice_id}

    monkeypatch.setattr(bexio, "invoice", one)
    got = bexio.invoices([3, 1, 2, 1])
    assert got[1] == {"id": 1} and got[3] == {"id": 3}
    assert isinstance(got[2], bexio.BexioError)
    assert bexio.invoices([]) == {}


def test_read_at_records_when_a_window_was_read(http):
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, [])
    assert bexio.read_at("2026-09-01", "2026-09-30") is None
    bexio.search_invoices("2026-09-01", "2026-09-30")
    assert bexio.read_at("2026-09-01", "2026-09-30") is not None


# ---- network ------------------------------------------------------------------


def test_search_sends_the_date_window_and_the_token(http):
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, [_raw(1, 7)])
    rows = bexio.search_invoices("2026-09-01", "2026-09-30")
    assert [r["id"] for r in rows] == [1]
    call = http.calls[0]
    assert call["json"] == [
        {"field": "is_valid_from", "value": "2026-09-01", "criteria": ">="},
        {"field": "is_valid_from", "value": "2026-09-30", "criteria": "<="},
    ]
    assert call["headers"]["Authorization"] == "Bearer pat-for-tests"
    assert call["timeout"] == bexio.TIMEOUT


def test_search_pages_until_a_short_page(http, monkeypatch):
    monkeypatch.setattr(bexio, "PAGE_SIZE", 2)

    def pages(json=None, params=None):
        start = params["offset"]
        return FakeResponse(200, [_raw(i, 1) for i in range(start, min(start + 2, 5))])

    http.routes[("POST", "/2.0/kb_invoice/search")] = pages
    assert [r["id"] for r in bexio.search_invoices("a", "b")] == [0, 1, 2, 3, 4]
    assert [c["params"]["offset"] for c in http.calls] == [0, 2, 4]


def test_search_stops_at_the_page_cap(http, monkeypatch):
    monkeypatch.setattr(bexio, "PAGE_SIZE", 1)
    monkeypatch.setattr(bexio, "MAX_PAGES", 2)
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, [_raw(1, 1)])
    assert len(bexio.search_invoices("a", "b")) == 2
    assert len(http.calls) == 2


def test_search_is_cached_until_fresh(http):
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, [])
    bexio.search_invoices("a", "b")
    bexio.search_invoices("a", "b")
    assert len(http.calls) == 1
    bexio.search_invoices("a", "b", fresh=True)
    assert len(http.calls) == 2


@pytest.mark.parametrize(
    "status, message",
    [
        (401, "rejected the access token"),
        (403, "no permission"),
        (404, "Not found"),
        (429, "rate limit"),
        (500, "HTTP 500"),
    ],
)
def test_http_errors_become_bexio_errors_without_the_token(http, status, message):
    http.routes[("GET", "/2.0/kb_invoice/5")] = FakeResponse(status)
    with pytest.raises(bexio.BexioError, match=message) as err:
        bexio.invoice(5)
    assert err.value.status == status
    assert "pat-for-tests" not in str(err.value)


def test_unreadable_json_is_a_bexio_error(http):
    http.routes[("GET", "/2.0/kb_invoice/5")] = FakeResponse(200, bad_json=True)
    with pytest.raises(bexio.BexioError, match="unreadable"):
        bexio.invoice(5)


@pytest.mark.parametrize(
    "exc, message",
    [(requests.exceptions.Timeout, "in time"), (requests.exceptions.ConnectionError, "reached")],
)
def test_network_failures_become_bexio_errors(monkeypatch, exc, message):
    monkeypatch.setattr(config, "BEXIO_PAT", "t")

    def fail(*a, **k):
        raise exc("down")

    monkeypatch.setattr(bexio.requests, "request", fail)
    with pytest.raises(bexio.BexioError, match=message):
        bexio.invoice(1)


def test_a_non_list_search_answer_is_rejected(http):
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, {"error": "?"})
    with pytest.raises(bexio.BexioError, match="unexpected"):
        bexio.search_invoices("a", "b")


def test_contact_names_is_one_search(http):
    http.routes[("POST", "/2.0/contact/search")] = FakeResponse(
        200,
        [
            {"id": 3, "name_1": "Privera AG"},
            {"id": 4, "name_1": "Muster", "name_2": "Anna"},
            {"id": 5},
        ],
    )
    assert bexio.contact_names([4, 3, None, 3, 5]) == {3: "Privera AG", 4: "Muster Anna", 5: "#5"}
    assert http.calls[0]["json"] == [{"field": "id", "value": [3, 4, 5], "criteria": "in"}]
    assert bexio.contact_names([]) == {}
    assert len(http.calls) == 1


def test_currencies_degrade_to_empty(http):
    assert bexio.currencies() == {}
    bexio.clear_cache()
    http.routes[("GET", "/3.0/currencies")] = FakeResponse(200, [{"id": 1, "name": "CHF"}])
    assert bexio.currencies() == {1: "CHF"}


def test_invoice_pdf_decodes_the_content(http):
    http.routes[("GET", "/2.0/kb_invoice/8/pdf")] = FakeResponse(
        200, {"name": "RE-8.pdf", "content": base64.b64encode(b"%PDF-1.7").decode()}
    )
    assert bexio.invoice_pdf(8) == (b"%PDF-1.7", "RE-8.pdf")


@pytest.mark.parametrize("body", [{"name": "x.pdf"}, {"content": "!!not base64!!"}, []])
def test_invoice_pdf_rejects_empty_or_broken_content(http, body):
    http.routes[("GET", "/2.0/kb_invoice/8/pdf")] = FakeResponse(200, body)
    with pytest.raises(bexio.BexioError):
        bexio.invoice_pdf(8)


def test_every_call_is_a_read(http):
    """nexora never writes to Bexio: only GETs and the search POSTs."""
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, [])
    http.routes[("POST", "/2.0/contact/search")] = FakeResponse(200, [])
    http.routes[("GET", "/3.0/currencies")] = FakeResponse(200, [])
    http.routes[("GET", "/2.0/kb_invoice/1")] = FakeResponse(200, {"id": 1})
    http.routes[("GET", "/2.0/kb_invoice/1/pdf")] = FakeResponse(
        200, {"content": base64.b64encode(b"x").decode()}
    )
    bexio.search_invoices("a", "b")
    bexio.contact_names([1])
    bexio.currencies()
    bexio.invoice(1)
    bexio.invoice_pdf(1)
    for call in http.calls:
        assert call["method"] == "GET" or call["path"].endswith("/search"), call


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(bexio, "_CACHE_MAX", 3)
    for i in range(5):
        bexio._cached(("k", i), 60, lambda i=i: i)
    assert len(bexio._cache) == 3


def test_a_long_lived_year_search_does_not_share_the_month_cache_entry(http):
    calls = []

    def answer(json=None, params=None):
        calls.append(json)
        return FakeResponse(200, [])

    http.routes[("POST", "/2.0/kb_invoice/search")] = answer
    bexio.search_invoices("2026-01-01", "2026-12-31", ttl=bexio.YEAR_TTL)
    bexio.search_invoices("2026-01-01", "2026-12-31")
    assert len(calls) == 2  # two entries, each with its own expiry


def test_outstanding_survives_an_unreadable_due_date():
    out = bexio.outstanding([_owed(1, 1, "soon")], [], [], {}, "2026-10-01")
    assert out["invoices"][0]["overdueDays"] == 0


def test_latest_before_rejects_a_payload_that_is_not_a_list(http):
    http.routes[("POST", "/2.0/kb_invoice/search")] = FakeResponse(200, {"error": "?"})
    with pytest.raises(bexio.BexioError):
        bexio.latest_before([7], "2026-09-01")
