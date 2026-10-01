"""Sydoc Finance: what was invoiced in Bexio (#423).

Read-only against Bexio -- nx_lib/bexio.py only searches and GETs. Which
Bexio contact belongs to which Finance client is fixed data in
dbo.FinanceBexioContacts (0141), set by migrations (0143); the panel only
reads it, so a link cannot be removed by a stray click.

Gates: finance.view reads the panel, an invoice's lines and its PDF (the
page is Sydoc's own accounting; finance.view already reads every billing
source unscoped, and is never granted to a customer profile). Linking a
contact changes what the page shows for everyone, so it needs
finance.month.edit, the code that already closes and reopens a month.

Bexio is read live and is not part of the month close: it is the system of
record for the invoice itself.
"""

import datetime as dt

from flask import Response, current_app, jsonify, request
from flask_babel import format_date, gettext

from .. import bexio
from ..db import engine_nexora_db
from ..extensions import limiter
from ..finance import billed_clients, month_key, parse_month
from ..security import require_permission

BEXIO_OFFICE_INVOICE = "https://office.bexio.com/index.php/kb_invoice/show/id/{id}"


def _message(e):
    """A BexioError as a translated sentence for the panel."""
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
        current_app.logger.warning(f"finance: could not read the Bexio contact links: {e}")
        return []


def _not_configured():
    return {
        "configured": False,
        "error": gettext("Bexio is not configured on this server (BEXIO_PAT)."),
    }


@require_permission("finance.view")
@limiter.limit("60 per minute")
def api_finance_bexio():
    year, month = parse_month(request.args.get("month"))
    date_from, date_to, (wy, wm) = bexio.invoice_window(year, month)
    window = {
        "from": date_from,
        "to": date_to,
        "label": format_date(dt.date(wy, wm, 1), "LLLL yyyy"),
    }
    if not bexio.configured():
        body = _not_configured()
        body.update(month=month_key(year, month), window=window)
        return jsonify(body)
    fresh = request.args.get("fresh") == "1"
    links = _links()
    try:
        raw = bexio.search_invoices(date_from, date_to, fresh=fresh)
        codes = bexio.currencies()
        invoices = [bexio.normalize_invoice(r, codes) for r in raw]
        ids = {i["contactId"] for i in invoices} | {link.contact_id for link in links}
        try:
            names = bexio.contact_names(ids, fresh=fresh)
        except bexio.BexioError as e:
            # Names are a convenience: without them the panel shows contact ids.
            current_app.logger.warning(f"finance: Bexio contact names unavailable: {e}")
            names = {}
    except bexio.BexioError as e:
        current_app.logger.warning(f"finance: Bexio read for {date_from}..{date_to} failed: {e}")
        return jsonify(
            {
                "configured": True,
                "month": month_key(year, month),
                "window": window,
                "error": _message(e),
                "detail": str(e),
            }
        )
    body = bexio.reconcile(billed_clients(), links, invoices, names)
    body.update(
        configured=True,
        month=month_key(year, month),
        window=window,
        clientNames=billed_clients(),
    )
    return jsonify(body)


@require_permission("finance.view")
@limiter.limit("120 per minute")
def api_finance_bexio_invoice(invoice_id):
    if not bexio.configured():
        return jsonify(_not_configured()), 503
    try:
        raw = bexio.invoice(invoice_id)
        inv = bexio.normalize_invoice(raw, bexio.currencies())
    except bexio.BexioError as e:
        status = 404 if e.status == 404 else 502
        return jsonify({"error": _message(e), "detail": str(e)}), status
    inv["positions"] = bexio.normalize_positions(raw.get("positions"))
    inv["bexioUrl"] = BEXIO_OFFICE_INVOICE.format(id=inv["id"])
    return jsonify(inv)


@require_permission("finance.view")
@limiter.limit("30 per minute")
def api_finance_bexio_pdf(invoice_id):
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
    app.add_url_rule(
        "/api/finance/bexio", endpoint="api_finance_bexio", view_func=api_finance_bexio
    )
    app.add_url_rule(
        "/api/finance/bexio/invoice/<int:invoice_id>",
        endpoint="api_finance_bexio_invoice",
        view_func=api_finance_bexio_invoice,
    )
    app.add_url_rule(
        "/api/finance/bexio/invoice/<int:invoice_id>/pdf",
        endpoint="api_finance_bexio_pdf",
        view_func=api_finance_bexio_pdf,
    )
