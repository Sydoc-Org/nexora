"""xlsx upload validation: real .xlsx passes, a renamed non-xlsx is rejected."""

import io

import openpyxl

from nx_lib.files import is_file_allowed


def _xlsx_bytes():
    wb = openpyxl.Workbook()
    wb.active.append(["PID", "Prepared"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_real_xlsx_is_allowed():
    assert is_file_allowed("prepared.xlsx", _xlsx_bytes()) is True


def test_pdf_bytes_renamed_to_xlsx_is_rejected():
    fake = io.BytesIO(b"%PDF-1.4 not really a spreadsheet")
    assert is_file_allowed("prepared.xlsx", fake) is False


def test_xlsx_extension_required():
    assert is_file_allowed("prepared.txt", _xlsx_bytes()) is False
