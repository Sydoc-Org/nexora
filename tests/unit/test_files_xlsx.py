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


def test_octet_stream_no_longer_accepted_for_xlsx(monkeypatch):
    """Security #193: application/octet-stream is libmagic's any-binary
    fallback, so accepting it for .xlsx collapsed the sniff to a bare
    extension check. A payload that sniffs as octet-stream must be rejected."""
    import nx_lib.files as files

    monkeypatch.setattr(files.magic, "from_buffer", lambda *a, **k: "application/octet-stream")
    assert is_file_allowed("prepared.xlsx", io.BytesIO(b"anything")) is False
