"""Read-only Bexio client for the Sydoc Finance invoice panel (#423).

Bexio is Sydoc's accounting system: invoices are written and priced there.
The Finance page counts what to bill; this module reads what *was* billed, so
the two can be read side by side. It never writes to Bexio -- every call is a
GET or a search POST (Bexio's search endpoints take their criteria as a POST
body but change nothing).

Two halves:

* **Network** (``search_invoices``, ``contact_names``, ``invoice``,
  ``invoice_pdf``, ``currencies``): thin wrappers over the REST API with a
  short in-process cache, raising ``BexioError`` with a reader-facing reason.
* **Pure** (``invoice_window``, ``normalize_invoice``, ``normalize_positions``,
  ``reconcile``): turn Bexio's payloads into what the page renders. No Flask,
  no network, unit-tested directly.

The token is ``BEXIO_PAT``; unset means ``configured()`` is False and nothing
here touches the network. It is read from ``nx_lib.config`` at call time so a
test can set it with monkeypatch.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import requests

API = "https://api.bexio.com"
TIMEOUT = 15
PAGE_SIZE = 500
MAX_PAGES = 10
CACHE_TTL = 300  # seconds; the panel's Refresh button bypasses it
CONTACT_TTL = 3600

# The invoice for billed month M is dated in month M + INVOICE_MONTH_OFFSET.
# An assumption until accounting confirms it (#423); the page names the window
# it searched, so a wrong offset is visible rather than silent.
INVOICE_MONTH_OFFSET = 1

# kb_item_status_id. Anything unknown is treated as issued (and shown as "other").
DRAFT = 7
PENDING = 8
PAID = 9
PARTIAL = 16
CANCELLED = 19
UNPAID = 31
STATUS_KEYS = {
    DRAFT: "draft",
    PENDING: "open",
    PAID: "paid",
    PARTIAL: "partial",
    CANCELLED: "cancelled",
    UNPAID: "unpaid",
}

# Client states on the panel.
INVOICED = "invoiced"
DRAFT_ONLY = "draft"
MISSING = "missing"
UNLINKED = "unlinked"


class BexioError(RuntimeError):
    """A Bexio call failed; ``str(e)`` is safe to show (never carries the token)."""

    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status = status


def _token():
    from . import config

    return config.BEXIO_PAT


def configured():
    return bool(_token())


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

_cache: OrderedDict = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 256


def _cached(key, ttl, loader, *, fresh=False):
    now = time.monotonic()
    if not fresh:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
    value = loader()
    with _cache_lock:
        _cache[key] = (now + ttl, value)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return value


def clear_cache():
    with _cache_lock:
        _cache.clear()


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------


def _request(method, path, *, json=None, params=None):
    token = _token()
    if not token:
        raise BexioError("Bexio is not configured (BEXIO_PAT is not set).")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    try:
        resp = requests.request(
            method, API + path, headers=headers, json=json, params=params, timeout=TIMEOUT
        )
    except requests.exceptions.Timeout as e:
        raise BexioError("Bexio did not answer in time.") from e
    except requests.exceptions.RequestException as e:
        raise BexioError("Bexio could not be reached.") from e
    if resp.status_code == 401:
        raise BexioError("Bexio rejected the access token.", status=401)
    if resp.status_code == 403:
        raise BexioError("The access token has no permission for this Bexio data.", status=403)
    if resp.status_code == 404:
        raise BexioError("Not found in Bexio.", status=404)
    if resp.status_code == 429:
        raise BexioError("Bexio's rate limit was hit; try again in a minute.", status=429)
    if not resp.ok:
        raise BexioError(f"Bexio answered HTTP {resp.status_code}.", status=resp.status_code)
    try:
        return resp.json()
    except ValueError as e:
        raise BexioError("Bexio returned an unreadable answer.") from e


def search_invoices(date_from, date_to, *, fresh=False):
    """Every invoice dated ``date_from`` .. ``date_to`` (ISO dates, inclusive)."""

    def load():
        criteria = [
            {"field": "is_valid_from", "value": date_from, "criteria": ">="},
            {"field": "is_valid_from", "value": date_to, "criteria": "<="},
        ]
        found = []
        for page in range(MAX_PAGES):
            batch = _request(
                "POST",
                "/2.0/kb_invoice/search",
                json=criteria,
                params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE, "order_by": "id"},
            )
            if not isinstance(batch, list):
                raise BexioError("Bexio returned an unexpected invoice list.")
            found.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
        return found

    return _cached(("invoices", date_from, date_to), CACHE_TTL, load, fresh=fresh)


def _contact_label(raw):
    name = " ".join(p for p in (raw.get("name_1"), raw.get("name_2")) if p)
    return name.strip() or f"#{raw.get('id')}"


def contact_names(ids, *, fresh=False):
    """{contact id: display name} for the given ids (one search, cached)."""
    wanted = sorted({int(i) for i in ids if i})
    if not wanted:
        return {}

    def load():
        rows = _request(
            "POST",
            "/2.0/contact/search",
            json=[{"field": "id", "value": wanted, "criteria": "in"}],
            params={"limit": PAGE_SIZE},
        )
        return {int(r["id"]): _contact_label(r) for r in rows if r.get("id") is not None}

    return _cached(("contacts", tuple(wanted)), CONTACT_TTL, load, fresh=fresh)


def currencies(*, fresh=False):
    """{currency id: code}; empty if Bexio will not say (codes then show blank)."""

    def load():
        try:
            rows = _request("GET", "/3.0/currencies")
        except BexioError:
            return {}
        return {int(r["id"]): r.get("name") or "" for r in rows if r.get("id") is not None}

    return _cached(("currencies",), CONTACT_TTL, load, fresh=fresh)


def purchase_bills(*, fresh=False):
    """Every purchase bill (supplier invoice) in Bexio, raw (``/4.0/purchase/bills``).

    Bexio pages them; Sydoc keeps a few hundred a year, so all of them are
    read and cached rather than searched (the endpoint filters on little).
    """

    def load():
        found = []
        for page in range(1, MAX_PAGES + 1):
            body = _request("GET", "/4.0/purchase/bills", params={"limit": PAGE_SIZE, "page": page})
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise BexioError("Bexio returned an unexpected bill list.")
            found.extend(body["data"])
            count = (body.get("paging") or {}).get("page_count") or 1
            if page >= count:
                break
        return found

    return _cached(("bills",), CACHE_TTL, load, fresh=fresh)


def normalize_bill(raw):
    """What Controlling reads of one purchase bill: net amount (excl. VAT) and month."""
    return {
        "id": str(raw.get("id") or ""),
        "nr": raw.get("document_no") or "",
        "vendor": " ".join(str(raw.get("vendor") or "").split()),
        "title": raw.get("title") or "",
        "date": _date(raw.get("bill_date")),
        "net": _money(_dec(raw.get("net"))),
        "gross": _money(_dec(raw.get("gross"))),
        "currency": raw.get("currency_code") or "",
        "status": str(raw.get("status") or "").lower(),
    }


def exchange_rate(currency_id, date, *, fresh=False):
    """CHF per one unit of ``currency_id`` in the month of ``date`` (ISO), as
    Bexio states it (its monthly average), or None when Bexio has none.
    Cached per currency and month: the rate of a past month does not move."""
    currency_id = int(currency_id)
    first = f"{str(date)[:7]}-01"

    def load():
        rows = _request(
            "GET", f"/3.0/currencies/{currency_id}/exchange_rates", params={"date": first}
        )
        for r in rows if isinstance(rows, list) else []:
            if (r.get("exchange_currency") or {}).get("name") == "CHF":
                factor = _dec(r.get("factor_nr_to_ratio") or r.get("factor_nr"))
                return factor if factor > 0 else None
        return None

    return _cached(("fx", currency_id, first), CONTACT_TTL, load, fresh=fresh)


def invoice(invoice_id, *, fresh=False):
    """One invoice with its positions (the raw Bexio payload)."""
    invoice_id = int(invoice_id)
    return _cached(
        ("invoice", invoice_id),
        CACHE_TTL,
        lambda: _request("GET", f"/2.0/kb_invoice/{invoice_id}"),
        fresh=fresh,
    )


def invoice_pdf(invoice_id):
    """(pdf bytes, file name) of one invoice. Not cached: PDFs are large."""
    invoice_id = int(invoice_id)
    data = _request("GET", f"/2.0/kb_invoice/{invoice_id}/pdf")
    content = data.get("content") if isinstance(data, dict) else None
    if not content:
        raise BexioError("Bexio returned no PDF for this invoice.")
    try:
        pdf = base64.b64decode(content, validate=True)
    except (ValueError, TypeError) as e:
        raise BexioError("Bexio returned an unreadable PDF.") from e
    return pdf, data.get("name") or f"invoice-{invoice_id}.pdf"


# --------------------------------------------------------------------------
# Pure
# --------------------------------------------------------------------------


def _shift(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def invoice_window(year, month, offset=INVOICE_MONTH_OFFSET):
    """(first day, last day, (year, month)) of the month the invoices for
    ``year``-``month`` are dated in; the days as ISO strings."""
    y, m = _shift(year, month, offset)
    ny, nm = _shift(y, m, 1)
    last = (dt.date(ny, nm, 1) - dt.timedelta(days=1)).day
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}", (y, m)


def _dec(value):
    if value in (None, ""):
        return Decimal(0)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _money(value):
    """A Decimal as a JSON number with cent precision."""
    return float(value.quantize(Decimal("0.01")))


def _date(value):
    return str(value)[:10] if value else None


def normalize_invoice(raw, currency_codes=None):
    """What the panel shows of one invoice. ``excl`` is ``total`` minus VAT,
    derived rather than read, so it does not depend on the invoice's VAT mode."""
    status_id = raw.get("kb_item_status_id")
    total = _dec(raw.get("total"))
    taxes = _dec(raw.get("total_taxes"))
    currency_id = raw.get("currency_id")
    return {
        "id": int(raw["id"]),
        "nr": raw.get("document_nr") or "",
        "title": raw.get("title") or "",
        "contactId": int(raw["contact_id"]) if raw.get("contact_id") is not None else None,
        # The Bexio project tells a customer's invoices apart (Controlling, #433).
        "projectId": int(raw["project_id"]) if raw.get("project_id") is not None else None,
        "date": _date(raw.get("is_valid_from")),
        "due": _date(raw.get("is_valid_to")),
        "status": STATUS_KEYS.get(status_id, "other"),
        "total": _money(total),
        "excl": _money(total - taxes),
        "currency": (currency_codes or {}).get(currency_id, "") if currency_id else "",
        "currencyId": int(currency_id) if currency_id is not None else None,
    }


def counts(inv):
    """Whether an invoice counts towards what was billed: issued, not cancelled."""
    return inv["status"] not in ("draft", "cancelled")


_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"<\s*(br|/p|/li|/div)\s*/?>", re.I)


def _plain(text):
    """Bexio position text is HTML; the panel shows it as plain text."""
    if not text:
        return ""
    text = _BREAK_RE.sub("\n", str(text))
    text = html.unescape(_TAG_RE.sub("", text))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def normalize_positions(raw_positions):
    """Invoice lines in order: articles / custom lines with quantity and price,
    text lines, subtotals and discounts. Page breaks are dropped."""
    out = []
    for p in raw_positions or []:
        kind = str(p.get("type") or "")
        if kind == "KbPositionPagebreak":
            continue
        line: dict = {"kind": "text", "text": _plain(p.get("text"))}
        if kind in ("KbPositionCustom", "KbPositionArticle"):
            line.update(
                kind="line",
                amount=float(_dec(p.get("amount"))),
                unit=p.get("unit_name") or "",
                unitPrice=_money(_dec(p.get("unit_price"))),
                discount=float(_dec(p.get("discount_in_percent"))),
                total=_money(_dec(p.get("position_total"))),
            )
        elif kind == "KbPositionSubtotal":
            line.update(kind="subtotal", total=_money(_dec(p.get("value"))))
        elif kind == "KbPositionDiscount":
            line.update(kind="discount", total=_money(-_dec(p.get("discount_total"))))
        if p.get("is_optional"):
            line["optional"] = True
        out.append(line)
    return out


def totals(invoices):
    """[{currency, total, excl, count}] over the invoices that count, per currency."""
    sums: dict[str, list] = {}
    for inv in invoices:
        if not counts(inv):
            continue
        acc = sums.setdefault(inv["currency"], [Decimal(0), Decimal(0), 0])
        acc[0] += Decimal(str(inv["total"]))
        acc[1] += Decimal(str(inv["excl"]))
        acc[2] += 1
    return [
        {"currency": c, "total": _money(t), "excl": _money(e), "count": n}
        for c, (t, e, n) in sorted(sums.items())
    ]


@dataclass(frozen=True)
class Link:
    client: str
    contact_id: int


def reconcile(clients, links, invoices, names):
    """The panel: every Finance client with its linked contacts and invoices.

    ``clients`` -- Finance client names in page order.
    ``links`` -- ``Link`` rows (client -> Bexio contact id).
    ``invoices`` -- normalized invoices of the window.
    ``names`` -- {contact id: name}.

    Only invoices to linked contacts are shown and totalled: Sydoc's Bexio also
    bills customers nexora has no Finance figures for, and those are not this
    page's business.
    """
    linked: dict[str, list] = {}
    for link in links:
        linked.setdefault(link.client, []).append(link.contact_id)
    claimed = {cid for client in clients for cid in linked.get(client, [])}
    invoices = [i for i in invoices if i["contactId"] in claimed]
    by_contact: dict[int | None, list] = {}
    for inv in sorted(invoices, key=lambda i: (i["date"] or "", i["nr"])):
        by_contact.setdefault(inv["contactId"], []).append(inv)
    rows = []
    for client in clients:
        ids = sorted(linked.get(client, []))
        mine = [inv for cid in ids for inv in by_contact.get(cid, [])]
        if not ids:
            state = UNLINKED
        elif any(counts(i) for i in mine):
            state = INVOICED
        elif any(i["status"] == "draft" for i in mine):
            state = DRAFT_ONLY
        else:
            state = MISSING
        rows.append(
            {
                "client": client,
                "contacts": [{"id": cid, "name": names.get(cid, f"#{cid}")} for cid in ids],
                "state": state,
                "invoices": mine,
                "totals": totals(mine),
            }
        )
    return {
        "clients": rows,
        "totals": totals(invoices),
        "drafts": sum(1 for i in invoices if i["status"] == "draft"),
        "count": len(invoices),
    }
