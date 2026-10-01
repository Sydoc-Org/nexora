"""Sydoc Billing (#436): what was invoiced in Bexio, next to what Finance counted.

The page is keyed by the **invoice month**: /billing?month=2026-09 lists the
invoices dated in September, which bill the Finance month August
(nx_lib/billing.py). It grew out of the Bexio panel that sat on Sydoc Finance
(#423) and replaces it.

Read-only against Bexio -- nx_lib/bexio.py only searches and GETs. Which
Bexio contact belongs to which Finance client is fixed data in
dbo.FinanceBexioContacts (0141), set by migrations (0143); nothing here
writes it, so a link cannot be removed by a stray click.

billing.view (0147) is the whole gate, including the Finance figures the page
compares with (/api/billing/figures/<key>): the page names every client's
invoices and reads the billing sources unscoped, so like finance.view it is
never granted to a customer profile.

Bexio is read live and is not part of the Finance month close: it is the
system of record for the invoice itself. The figures it is compared with are
served from the month-close snapshot once the billed month is closed.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from flask import Response, abort, current_app, jsonify, render_template, request
from flask_babel import format_date, format_time, gettext

from .. import bexio
from .. import billing as bill
from ..db import engine_nexora_db
from ..extensions import limiter
from ..finance import SECTIONS_BY_KEY, billed_clients, month_key, parse_month, shift_month
from ..security import page_visibility, require_permission
from .finance import _closed_info, _closed_safe, _section_payload

BEXIO_OFFICE_INVOICE = "https://office.bexio.com/index.php/kb_invoice/show/id/{id}"
LOCAL_TZ = ZoneInfo("Europe/Zurich")


def _message(e):
    """A BexioError as a translated sentence for the page."""
    by_status: dict[int | None, str] = {
        401: gettext("Bexio rejected the access token."),
        403: gettext("The access token has no permission to read invoices in Bexio."),
        404: gettext("Not found in Bexio."),
        429: gettext("Bexio's rate limit was hit; try again in a minute."),
    }
    return by_status.get(getattr(e, "status", None), gettext("Could not read Bexio."))


def _links():
    """Every client -> contact link; [] when the table cannot be read (logged)."""
    if engine_nexora_db is None:
        return []
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT Client, ContactId FROM dbo.FinanceBexioContacts")
            return [bexio.Link(r[0], int(r[1])) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.warning(f"billing: could not read the Bexio contact links: {e}")
        return []


def _not_configured():
    return {
        "configured": False,
        "error": gettext("Bexio is not configured on this server (BEXIO_PAT)."),
    }


def _month_label(year, month):
    return format_date(dt.date(year, month, 1), "LLLL yyyy")


def _invoice_month(today=None):
    """(year, month) of ?month=, the invoice month, clamped to the pickable range."""
    today = today or dt.date.today()
    year, month = parse_month(request.args.get("month"), today)
    keys = bill.invoice_month_keys(today)
    if keys and month_key(year, month) < keys[-1]:
        oldest = keys[-1]
        return int(oldest[:4]), int(oldest[5:])
    return year, month


def _billed(year, month):
    """What the invoice month bills: {month, label, closed} of the Finance month."""
    by, bm = bill.billed_month(year, month)
    key = month_key(by, bm)
    return {
        "month": key,
        "label": _month_label(by, bm),
        "name": format_date(dt.date(by, bm, 1), "LLLL"),
        "closed": _closed_info(_closed_safe(key)),
    }


def _with_url(inv):
    inv["bexioUrl"] = BEXIO_OFFICE_INVOICE.format(id=inv["id"])
    return inv


def _names(ids, fresh):
    try:
        return bexio.contact_names(ids, fresh=fresh)
    except bexio.BexioError as e:
        # Names are a convenience: without them the page shows contact ids.
        current_app.logger.warning(f"billing: Bexio contact names unavailable: {e}")
        return {}


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------


@require_permission("billing.view")
def billing():
    today = dt.date.today()
    year, month = _invoice_month(today)
    key = month_key(year, month)
    keys = bill.invoice_month_keys(today)
    prev_key = month_key(*shift_month(year, month, -1))
    is_current = (year, month) == (today.year, today.month)
    translate = gettext  # an alias, so pybabel does not extract the variable as a msgid
    clients = bill.client_descriptors(translate)
    billed = _billed(year, month)
    return render_template(
        "billing.html",
        page_visibility=page_visibility(),
        month=key,
        month_label=_month_label(year, month),
        month_name=format_date(dt.date(year, month, 1), "LLLL"),
        month_year=str(year),
        today=today.isoformat(),
        prev_month=prev_key if prev_key in keys else None,
        next_month=None if is_current else month_key(*shift_month(year, month, 1)),
        is_current_month=is_current,
        billed=billed,
        months=keys,
        internal_clients=[c for c in clients if c["group"] == "internal"],
        external_clients=[c for c in clients if c["group"] != "internal"],
    )


# --------------------------------------------------------------------------
# APIs
# --------------------------------------------------------------------------


def _latest(contact_ids, date_from, codes, fresh):
    """{nr, date, status} of a missing client's latest invoice, or None."""
    try:
        raw = bexio.latest_before(contact_ids, date_from, fresh=fresh)
    except bexio.BexioError as e:
        current_app.logger.warning(f"billing: latest invoice before {date_from} unavailable: {e}")
        return None
    if not raw:
        return None
    inv = bexio.normalize_invoice(raw, codes)
    return {"nr": inv["nr"], "date": inv["date"], "status": inv["status"]}


@require_permission("billing.view")
@limiter.limit("60 per minute")
def api_billing_month():
    """The invoices dated in the invoice month, per Finance client, each with
    its lines; invoices to unlinked contacts apart (``others``)."""
    year, month = _invoice_month()
    by, bm = bill.billed_month(year, month)
    date_from, date_to, _ym = bexio.invoice_window(by, bm)
    window = {"from": date_from, "to": date_to, "label": _month_label(year, month)}
    base = {"month": month_key(year, month), "window": window, "billed": _billed(year, month)}
    if not bexio.configured():
        return jsonify({**_not_configured(), **base})
    fresh = request.args.get("fresh") == "1"
    links = _links()
    try:
        raw = bexio.search_invoices(date_from, date_to, fresh=fresh)
        codes = bexio.currencies()
    except bexio.BexioError as e:
        current_app.logger.warning(f"billing: Bexio read for {date_from}..{date_to} failed: {e}")
        return jsonify({"configured": True, **base, "error": _message(e), "detail": str(e)})
    invoices = [bexio.normalize_invoice(r, codes) for r in raw]
    names = _names({i["contactId"] for i in invoices} | {k.contact_id for k in links}, fresh)
    body = bexio.reconcile(billed_clients(), links, invoices, names)

    mine = [inv for c in body["clients"] for inv in c["invoices"]]
    full = bexio.invoices([inv["id"] for inv in mine], fresh=fresh)
    for inv in mine:
        got = full.get(inv["id"])
        if isinstance(got, dict):
            inv["positions"] = bexio.normalize_positions(got.get("positions"))
        else:
            inv["positions"] = None
            inv["positionsError"] = _message(got)
        _with_url(inv)
    for inv in body["others"]:
        _with_url(inv)
    for c in body["clients"]:
        c["key"] = bill.client_key(c["client"])
        if c["state"] == bexio.MISSING:
            c["last"] = _latest([x["id"] for x in c["contacts"]], date_from, codes, fresh)

    at = bexio.read_at(date_from, date_to)
    body.update(
        configured=True,
        readAt=format_time(at.astimezone(LOCAL_TZ), "HH:mm", rebase=False) if at else None,
        **base,
    )
    return jsonify(body)


@require_permission("billing.view")
@limiter.limit("240 per minute")
def api_billing_figures(key):
    """The Finance figures of the billed month for one section, reduced to what
    an invoice line is compared with. The BPS section answers with the billed
    hours per client instead. A closed month is served from its snapshot."""
    section = SECTIONS_BY_KEY.get(key)
    if section is None:
        abort(404)
    by, bm = bill.billed_month(*_invoice_month())
    mkey = month_key(by, bm)
    snapshot = _closed_safe(mkey).get(key)
    payload = snapshot["payload"] if snapshot else _section_payload(section, by, bm)
    if key == bill.BPS_SECTION:
        body = {"key": key, "error": payload.get("error"), "hours": {}}
        if not payload.get("error"):
            body["hours"] = bill.billed_hours(payload, gettext("Billed hours (BPS)"))
    else:
        body = bill.section_figures(payload)
    body.update(month=mkey, closed=bool(snapshot))
    return jsonify(body)


@require_permission("billing.view")
@limiter.limit("60 per minute")
def api_billing_outstanding():
    """Every invoice still owed in Bexio, whatever its month, oldest due first."""
    today = dt.date.today()
    base = {"asOf": today.isoformat()}
    if not bexio.configured():
        return jsonify({**_not_configured(), **base})
    fresh = request.args.get("fresh") == "1"
    try:
        raw = bexio.search_outstanding(fresh=fresh)
        codes = bexio.currencies()
    except bexio.BexioError as e:
        current_app.logger.warning(f"billing: Bexio outstanding read failed: {e}")
        return jsonify({"configured": True, **base, "error": _message(e), "detail": str(e)})
    invoices = [_with_url(bexio.normalize_invoice(r, codes)) for r in raw]
    links = _links()
    names = _names({i["contactId"] for i in invoices}, fresh)
    body = bexio.outstanding(invoices, links, billed_clients(), names, today.isoformat())
    body.update(configured=True, **base)
    return jsonify(body)


@require_permission("billing.view")
@limiter.limit("60 per minute")
def api_billing_months():
    """The picker's status line for one year: {'YYYY-MM': 'running' | 'all' |
    'missing:<n>'}, from one search over the year's invoices (cached)."""
    today = dt.date.today()
    try:
        year = int(request.args.get("year") or today.year)
    except ValueError:
        year = today.year
    year = max(min(year, today.year), 2000)
    if not bexio.configured():
        return jsonify({"year": year, "states": {}, "configured": False})
    try:
        raw = bexio.search_invoices(f"{year:04d}-01-01", f"{year:04d}-12-31", ttl=bexio.YEAR_TTL)
    except bexio.BexioError as e:
        current_app.logger.warning(f"billing: Bexio read of {year} failed: {e}")
        return jsonify({"year": year, "states": {}, "error": _message(e)})
    invoices = [bexio.normalize_invoice(r) for r in raw]
    states = bexio.month_states(invoices, _links(), billed_clients(), year, today.isoformat())
    return jsonify({"year": year, "states": states})


@require_permission("billing.view")
@limiter.limit("120 per minute")
def api_billing_invoice(invoice_id):
    if not bexio.configured():
        return jsonify(_not_configured()), 503
    try:
        raw = bexio.invoice(invoice_id)
        inv = bexio.normalize_invoice(raw, bexio.currencies())
    except bexio.BexioError as e:
        status = 404 if e.status == 404 else 502
        return jsonify({"error": _message(e), "detail": str(e)}), status
    inv["positions"] = bexio.normalize_positions(raw.get("positions"))
    return jsonify(_with_url(inv))


@require_permission("billing.view")
@limiter.limit("30 per minute")
def api_billing_pdf(invoice_id):
    if not bexio.configured():
        return jsonify(_not_configured()), 503
    try:
        pdf, name = bexio.invoice_pdf(invoice_id)
    except bexio.BexioError as e:
        status = 404 if e.status == 404 else 502
        return jsonify({"error": _message(e), "detail": str(e)}), status
    safe = "".join(c for c in name if c.isalnum() or c in "._- ") or f"invoice-{invoice_id}.pdf"
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe}"',
            # Private accounting data: never cache (tests/unit/test_static_v_lint.py).
            "Cache-Control": "no-store",
        },
    )


def register_routes(app):
    app.add_url_rule("/billing", endpoint="billing", view_func=billing)
    app.add_url_rule(
        "/api/billing/month", endpoint="api_billing_month", view_func=api_billing_month
    )
    app.add_url_rule(
        "/api/billing/figures/<key>", endpoint="api_billing_figures", view_func=api_billing_figures
    )
    app.add_url_rule(
        "/api/billing/outstanding",
        endpoint="api_billing_outstanding",
        view_func=api_billing_outstanding,
    )
    app.add_url_rule(
        "/api/billing/months", endpoint="api_billing_months", view_func=api_billing_months
    )
    app.add_url_rule(
        "/api/billing/invoice/<int:invoice_id>",
        endpoint="api_billing_invoice",
        view_func=api_billing_invoice,
    )
    app.add_url_rule(
        "/api/billing/invoice/<int:invoice_id>/pdf",
        endpoint="api_billing_pdf",
        view_func=api_billing_pdf,
    )
