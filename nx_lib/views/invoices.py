"""Invoices and the Bexio API integration that backs them.

ARCHIVED (#177) — the page is retired. `register_routes()` is deliberately NOT
called from `nx_lib/__init__.py`, so `/invoices`, `/api/invoices` and
`/invoice/<id>/pdf` all 404; the sidebar entry and Ctrl+K command are gone and
`page_visibility()` no longer exposes `invoicesPagePerm`. The `invoices.*`
permission rows are left in place, and `dbo.ClientInvoices` was renamed to
`dbo.decapitated_ClientInvoices` (migration 0056) — the two DB helpers below
still name the old table, so reviving the page means all three: re-register the
routes, restore `invoicesPagePerm` + the nav entries, and rename the table back.
Kept in tree (with its helper tests) because the Bexio integration is the only
copy of that code.
"""

import base64
import json
from datetime import datetime, timedelta

import requests
from flask import (
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _

from ..config import BEXIO_PAT
from ..db import engine_nexora_db
from ..security import PermissionDenied, has_permission, page_visibility, require_permission

# --------------------------------- bexio ---------------------------------- #


def get_allowed_client_details():
    conn = None
    cursor = None
    try:
        perms = session.get("permissions", [])
        prefix = "invoices.view."
        allowed_names = sorted({perm.split(".")[-1] for perm in perms if perm.startswith(prefix)})

        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        clients = []

        for name in allowed_names:
            cursor.execute(
                "SELECT bexioClientId, ClientName FROM ClientInvoices WHERE ClientName = ?",
                (name,),
            )
            row = cursor.fetchone()
            if row:
                clients.append({"id": row[0], "name": row[1]})

        return clients
    except Exception as e:
        current_app.logger.error(f"Error fetching client details: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _is_paid_status(status_id):
    """Single source of truth for what counts as 'Paid' in Bexio's
    kb_item_status_id. Any other status (draft, cancelled, or any other
    Bexio code) is 'Open' - both map_invoice_status (the label) and
    search_bexio_invoices (the filter) must derive from this same rule so
    they never drift apart (Task 22)."""
    return status_id == 9


def map_invoice_status(status_id):
    if _is_paid_status(status_id):
        return {"text": _("Paid"), "color": "green"}
    return {"text": _("Open"), "color": "blue"}


def search_bexio_invoices(client_ids, date_from, date_to, search_nr=None, status=None):
    url = "https://api.bexio.com/2.0/kb_invoice/search"
    access_token = BEXIO_PAT
    if not access_token:
        current_app.logger.error("BEXIO_PAT is not set.")
        return []

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    all_invoices = []
    for client_id in client_ids:
        payload = [
            {"field": "contact_id", "value": str(client_id), "criteria": "="},
            {"field": "is_valid_from", "value": date_from, "criteria": ">="},
            {"field": "is_valid_to", "value": date_to, "criteria": "<="},
        ]

        if search_nr:
            payload.append({"field": "document_nr", "value": f"%{search_nr}%", "criteria": "LIKE"})

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            invoices = response.json()

            if status:
                # "Paid" is the exact-match id 9; "Open" is everything else
                # that map_invoice_status would label "Open" - derived from
                # the same _is_paid_status predicate so the filter can never
                # disagree with the label (Task 22).
                status_predicates = {
                    "Paid": _is_paid_status,
                    "Open": lambda sid: not _is_paid_status(sid),
                }
                predicate = status_predicates.get(status)
                if predicate:
                    invoices = [inv for inv in invoices if predicate(inv.get("kb_item_status_id"))]

            for inv in invoices:
                inv["status_info"] = map_invoice_status(inv.get("kb_item_status_id"))
                try:
                    inv["total"] = f"{float(inv['total']):.2f}"
                except (ValueError, TypeError):
                    inv["total"] = "0.00"
            all_invoices.extend(invoices)

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Bexio API search failed for client {client_id}: {e}")
            continue
        except json.JSONDecodeError:
            current_app.logger.error(f"Bexio API returned invalid JSON for client {client_id}.")
            continue
    return all_invoices


def get_bexio_invoice_pdf(invoice_id):
    url = f"https://api.bexio.com/2.0/kb_invoice/{invoice_id}/pdf"
    access_token = BEXIO_PAT
    if not access_token:
        current_app.logger.error("BEXIO_PAT is not set.")
        return None, None

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        content = data.get("content")
        name = data.get("name")

        if not content or not name:
            current_app.logger.error(
                f"Bexio API response for PDF {invoice_id} missing content or name."
            )
            return None, None

        return base64.b64decode(content), name

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Bexio API PDF fetch failed for {invoice_id}: {e}")
        return None, None


def get_bexio_invoice_contact_id(invoice_id):
    """Fetch just the owning contact_id for an invoice.

    Used by download_invoice_pdf to verify the caller is scoped to the client
    that owns the invoice before releasing the PDF (the kb_invoice/<id>/pdf
    endpoint response has no contact_id, so this is a separate lookup).
    """
    url = f"https://api.bexio.com/2.0/kb_invoice/{invoice_id}"
    access_token = BEXIO_PAT
    if not access_token:
        current_app.logger.error("BEXIO_PAT is not set.")
        return None

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("contact_id")
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Bexio API invoice fetch failed for {invoice_id}: {e}")
        return None
    except json.JSONDecodeError:
        current_app.logger.error("Bexio API returned invalid JSON.")
        return None


def get_bexio_client_ids():
    conn = None
    cursor = None
    try:
        perms = session.get("permissions", [])
        prefix = "invoices.view."
        allowed_client_invoice_views = sorted(
            {perm.split(".")[-1] for perm in perms if perm.startswith(prefix)}
        )

        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        client_ids = []
        for aciv in allowed_client_invoice_views:
            cursor.execute(
                "SELECT bexioClientId FROM ClientInvoices WHERE ClientName = ?",
                aciv,
            )
            row = cursor.fetchone()
            if row:
                client_ids.append(row[0])
        return client_ids
    except Exception as e:
        current_app.logger.error(f"Error fetching Bexio client ids: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# --------------------------------- routes --------------------------------- #


@require_permission("invoices.view")
def invoices():
    try:
        if "username" not in session:
            return redirect(url_for("login"))

        logged_in_user = session.get("username", "Unknown")
        userid = session.get("userid", "Unknown")

        clients = get_allowed_client_details()
        search_nr_perm = has_permission("invoices.filter.invoiceid")
        search_nr = request.args.get("search", "") if search_nr_perm else None
        status_perm = has_permission("invoices.filter.status")
        status = request.args.get("status", "") if status_perm else None
        date_perm = has_permission("invoices.filter.date")
        date_from = (
            request.args.get(
                "dateFrom", (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            )
            if date_perm
            else (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        )
        date_to = (
            request.args.get("dateTo", datetime.now().strftime("%Y-%m-%d"))
            if date_perm
            else datetime.now().strftime("%Y-%m-%d")
        )

        return render_template(
            "archive/invoices.html",
            logged_in_user=logged_in_user,
            userid=userid,
            search=search_nr,
            status=status,
            dateFrom=date_from,
            dateTo=date_to,
            search_nr_perm=search_nr_perm,
            status_perm=status_perm,
            date_perm=date_perm,
            pageV=page_visibility(),
            clients=clients,
        )
    except Exception:
        return render_template("500.html")


@require_permission("invoices.view")
def api_invoices():
    try:
        if "username" not in session:
            return jsonify({"error": _("Not authorized")}), 401

        selected_client_id = request.args.get("client_id")
        search_nr = (
            request.args.get("search", "") if has_permission("invoices.filter.invoiceid") else None
        )
        status = (
            request.args.get("status", "") if has_permission("invoices.filter.status") else None
        )
        date_from = (
            request.args.get(
                "dateFrom", (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            )
            if has_permission("invoices.filter.date")
            else (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        )
        date_to = (
            request.args.get("dateTo", datetime.now().strftime("%Y-%m-%d"))
            if has_permission("invoices.filter.date")
            else datetime.now().strftime("%Y-%m-%d")
        )

        allowed_ids = get_bexio_client_ids()
        target_ids = []
        if selected_client_id:
            try:
                sel_id = int(selected_client_id)
                if sel_id in allowed_ids:
                    target_ids = [sel_id]
                else:
                    return jsonify([])
            except ValueError:
                target_ids = allowed_ids
        else:
            target_ids = allowed_ids

        if not target_ids:
            return jsonify([])

        invoices_list = search_bexio_invoices(
            client_ids=target_ids,
            date_from=date_from,
            date_to=date_to,
            search_nr=search_nr,
            status=status,
        )
        return jsonify(invoices_list)

    except Exception:
        return jsonify({"error": "Failed to fetch invoices"}), 500


@require_permission("invoices.download")
def download_invoice_pdf(invoice_id):
    if "username" not in session:
        return redirect(url_for("login"))

    # IDOR guard: invoices.download is a blanket permission, so scope the
    # actual download to the invoices the caller is allowed to see — same
    # trust boundary api_invoices already enforces via get_bexio_client_ids().
    contact_id = get_bexio_invoice_contact_id(invoice_id)
    allowed_ids = set(get_bexio_client_ids() or [])
    if contact_id is None or contact_id not in allowed_ids:
        raise PermissionDenied()

    try:
        pdf_content, pdf_name = get_bexio_invoice_pdf(invoice_id)

        if pdf_content and pdf_name:
            return Response(
                pdf_content,
                mimetype="application/pdf",
                headers={"Content-Disposition": f"attachment;filename={pdf_name}"},
            )
        flash(_("Could not download PDF. File not found or API error."), "error")
        return redirect(url_for("invoices"))

    except Exception as e:
        current_app.logger.error(f"Failed to download invoice PDF {invoice_id}: {e}")
        flash(_("An unexpected error occurred while downloading the PDF."), "error")
        return redirect(url_for("invoices"))


def register_routes(app):
    app.add_url_rule("/invoices", endpoint="invoices", view_func=invoices)
    app.add_url_rule("/api/invoices", endpoint="api_invoices", view_func=api_invoices)
    app.add_url_rule(
        "/invoice/<int:invoice_id>/pdf",
        endpoint="download_invoice_pdf",
        view_func=download_invoice_pdf,
    )
