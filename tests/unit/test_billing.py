"""nx_lib.billing: the mapping between Sydoc Billing and Sydoc Finance (#436).

Pure: the invoice month -> billed month rule, the pickable months, the client
rows and the reduction of a Finance payload to the figures an invoice line is
compared with (billed BPS hours per client included).
"""

import datetime as dt

from nx_lib import billing
from nx_lib.finance import SECTIONS_BY_KEY, billed_clients


def test_an_invoice_month_bills_the_month_before():
    assert billing.billed_month(2026, 9) == (2026, 8)
    assert billing.billed_month(2026, 1) == (2025, 12)


def test_invoice_months_run_from_now_back_to_the_one_billing_finances_oldest():
    keys = billing.invoice_month_keys(dt.date(2026, 10, 1))
    assert keys[0] == "2026-10"
    assert keys[-1] == "2023-12"  # bills Nov 2023, Finance's oldest month (36 back)
    assert keys == sorted(keys, reverse=True)


def test_every_billed_client_has_a_row_with_its_sections():
    rows = billing.client_descriptors()
    assert [r["client"] for r in rows] == billed_clients()
    privera = next(r for r in rows if r["client"] == "Privera")
    assert privera["key"] == "privera" and privera["sections"][0] == "privera_posteingang"
    assert all(SECTIONS_BY_KEY[k].client == r["client"] for r in rows for k in r["sections"])
    assert "bps" not in [k for r in rows for k in r["sections"]]
    assert next(r for r in rows if r["client"] == "Compass Group")["key"] == "compass-group"


def test_section_figures_flatten_every_block():
    payload = {
        "key": "bucherer",
        "client": "Bucherer",
        "title": "EasyTax",
        "error": None,
        "blocks": [
            {"figures": [{"code": "a", "label": "Imported", "value": 12}]},
            {"figures": [{"code": "b", "label": "Exported", "value": 9}]},
        ],
    }
    out = billing.section_figures(payload)
    assert out["title"] == "EasyTax" and out["error"] is None
    assert out["figures"] == [
        {"label": "Imported", "value": 12, "unit": None},
        {"label": "Exported", "value": 9, "unit": None},
    ]
    assert billing.section_figures({"key": "x", "error": "down"})["figures"] == []


def _bps_payload(rows):
    columns = [
        "Datum",
        "Kunde",
        "Projektpaket",
        "Aufgabe",
        "Benutzer",
        "Stunden",
        "Beschreibung",
        "billed",
    ]
    return {
        "bookings": {
            "columns": [{"field": c} for c in columns],
            "groups": [{"key": "x", "rows": rows}],
        }
    }


def test_billed_hours_per_client_split_for_privera():
    rows = [
        ["2026-08-03", "Frigemo", "Support", "Support", "A", 1.1, "", 1.25],
        ["2026-08-04", "Frigemo", "Support", "Support", "B", 0.5, "", 0.5],
        ["2026-08-05", "Privera", "Tagesgeschäft Posteingang", "Support", "A", 2.0, "", 2.0],
        ["2026-08-06", "Privera", "Neuzugänge", "Support", "A", 0.2, "", 0.25],
    ]
    out = billing.billed_hours(_bps_payload(rows), "Billed hours (BPS)")
    assert out["Frigemo"] == [{"label": "Billed hours (BPS)", "value": 1.75, "unit": "h"}]
    assert [(f["label"], f["value"]) for f in out["Privera"]] == [
        ("Posteingang", 2),
        ("Neuzugänge", 0.25),
    ]
