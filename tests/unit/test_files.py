"""Unit tests for nx_lib.files — MIME sniffing via libmagic."""

from io import BytesIO

from nx_lib.files import is_file_allowed

# Tiny but valid PDF (1.4) — accepted by libmagic as application/pdf
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF\n"

# 1x1 transparent PNG
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_is_file_allowed_pdf():
    assert is_file_allowed("invoice.pdf", BytesIO(PDF_BYTES)) is True


def test_is_file_allowed_png():
    assert is_file_allowed("photo.png", BytesIO(PNG_BYTES)) is True


def test_is_file_allowed_extension_mismatch():
    """Extension says PDF, libmagic detects PNG — rejected."""
    assert is_file_allowed("evil.pdf", BytesIO(PNG_BYTES)) is False


def test_is_file_allowed_no_extension():
    assert is_file_allowed("noextension", BytesIO(PDF_BYTES)) is False


def test_is_file_allowed_unknown_extension():
    assert is_file_allowed("script.exe", BytesIO(b"MZ\x90\x00")) is False
