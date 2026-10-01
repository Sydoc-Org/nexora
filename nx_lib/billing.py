"""Sydoc Billing (#436): what was invoiced in Bexio, next to what Finance counted.

Flask-free. The page is keyed by the **invoice month**: the invoices dated in
month M bill the Finance month M - bexio.INVOICE_MONTH_OFFSET. This module
holds the mapping between the two pages -- which Finance sections belong to
which Bexio client, the client's key on the page -- and reduces a Finance
section payload to the figures an invoice line is compared with.

The comparison itself (the ticks) runs in the browser once both sides are in
(static/js/billing.js): an exact match of a line's quantity against a figure,
hours against hours and counts against counts. No line-to-figure mapping
exists, so it is a heuristic and the page says so.
"""

from __future__ import annotations

from decimal import Decimal

from . import bexio, finance_export
from .finance import (
    SECTIONS,
    SECTIONS_BY_KEY,
    SERVICES,
    billed_clients,
    month_key,
    month_options,
    shift_month,
)

#: The Finance section whose bookings carry the billed BPS hours.
BPS_SECTION = "bps"


def billed_month(year, month, offset=bexio.INVOICE_MONTH_OFFSET):
    """The Finance month the invoices dated in ``year``-``month`` bill."""
    return shift_month(year, month, -offset)


def invoice_month_keys(today, offset=bexio.INVOICE_MONTH_OFFSET):
    """The pickable invoice months, newest first: the current month back to the
    month that bills Finance's oldest month."""
    out = []
    for _key, y, m in month_options(today):
        iy, im = shift_month(y, m, offset)
        if (iy, im) <= (today.year, today.month):
            out.append(month_key(iy, im))
    return out


def client_key(client):
    """A client's id on the page (``#bill-<key>``): 'Elektro-Material' -> 'elektro-material'."""
    return finance_export.slug(client)


def client_sections():
    """{client: [Finance section keys]} in page order, services left out."""
    out: dict[str, list[str]] = {c: [] for c in billed_clients()}
    for s in SECTIONS:
        if s.group != SERVICES:
            out[s.client].append(s.key)
    return out


def client_descriptors(translate=lambda s: s):
    """The static shape of the page: one entry per billed client, in Finance order."""
    out = []
    for client, keys in client_sections().items():
        first = SECTIONS_BY_KEY[keys[0]]
        out.append(
            {
                "client": client,
                "key": client_key(client),
                "group": first.group,
                "nav": translate(first.nav) if first.nav else client,
                "tile": client[:2],
                "sections": keys,
            }
        )
    return out


def _figure(label, value, unit=None):
    return {"label": label, "value": value, "unit": unit}


def section_figures(payload):
    """A Finance section payload reduced to what Billing compares with:
    {key, client, title, error, figures: [{label, value, unit}]}."""
    figures = [
        _figure(f["label"], f["value"])
        for block in payload.get("blocks") or []
        for f in block.get("figures") or []
    ]
    return {
        "key": payload.get("key"),
        "client": payload.get("client"),
        "title": payload.get("title"),
        "error": payload.get("error"),
        "figures": figures,
    }


def billed_hours(payload, label):
    """{client: [{label, value, unit: 'h'}]} of the billed BPS hours in the BPS
    section payload, one entry per invoice sheet: a client billed on one
    invoice gets ``label``; a split client (Privera) one entry per package,
    named after the package."""
    section = SECTIONS_BY_KEY[BPS_SECTION]
    out: dict[str, list] = {}
    for sheet in finance_export.sheets(payload, section.bookings):
        name = sheet.title
        if name.casefold().startswith(sheet.client.casefold()):
            name = name[len(sheet.client) :].strip()
        out.setdefault(sheet.client, []).append(_figure(name or label, _number(sheet.billed), "h"))
    return out


def _number(value: Decimal):
    return int(value) if value == value.to_integral_value() else float(value)
