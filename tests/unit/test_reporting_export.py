"""Unit tests for nx_lib.reporting.export — rows → xlsx bytes."""

import io

from openpyxl import load_workbook

from nx_lib.reporting.export import rows_to_xlsx


def test_rows_to_xlsx_uses_custom_headers_and_title():
    columns = [
        {"field": "doctype", "header": "Document type"},
        {"field": "pages", "header": "Pages"},
    ]
    rows = [["Invoice", 3], ["Letter", 1]]
    data = rows_to_xlsx(columns, rows, title="Q1 report")
    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws["A1"].value == "Document type"
    assert ws["B1"].value == "Pages"
    assert ws["A2"].value == "Invoice"
    assert ws["B3"].value == 1


def test_rows_to_xlsx_falls_back_to_field_when_no_header():
    columns = [{"field": "doctype", "header": None}]
    data = rows_to_xlsx(columns, [["x"]], title="t")
    ws = load_workbook(io.BytesIO(data)).active
    assert ws["A1"].value == "doctype"


def test_rows_to_xlsx_returns_bytes():
    data = rows_to_xlsx([{"field": "a", "header": "A"}], [], title="t")
    assert isinstance(data, bytes | bytearray) and len(data) > 0
