"""Unit tests for the Octo media helpers: internal-host URL rewriting and PDF
page rasterisation. All offline -- no network, no Flask app context."""

import io

from PIL import Image

from nx_lib.octo import _media_url_for_gateway, pdf_page_count, render_pdf_page_jpeg

GW = "vm-mobgen02.sydoc.ch"


def test_bare_internal_host_is_rewritten_to_gateway():
    url = (
        "https://mobscn02/api/documentservice/api/DocumentService/Streams/abc/Storage/1/Type/MEDIA"
    )
    out = _media_url_for_gateway(url, GW)
    assert out == (
        "https://vm-mobgen02.sydoc.ch/api/documentservice/api/DocumentService/Streams/abc/Storage/1/Type/MEDIA"
    )


def test_fqdn_host_is_left_untouched():
    url = "https://int-dps.sydoc.ch/api/documentservice/x/MEDIA"
    assert _media_url_for_gateway(url, GW) == url


def test_fragment_and_query_preserved_on_rewrite():
    url = "https://mobscn02/x/MEDIA?a=1#page=3"
    assert _media_url_for_gateway(url, GW) == "https://vm-mobgen02.sydoc.ch/x/MEDIA?a=1#page=3"


def test_empty_domain_is_noop():
    url = "https://mobscn02/x/MEDIA"
    assert _media_url_for_gateway(url, "") == url


def _one_page_pdf_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (120, 160), "white").save(buf, format="PDF")
    return buf.getvalue()


def test_pdf_page_count_and_render():
    pdf = _one_page_pdf_bytes()
    assert pdf_page_count(pdf) == 1
    jpeg = render_pdf_page_jpeg(pdf, 0)
    assert jpeg[:2] == b"\xff\xd8"  # JPEG SOI marker
    assert len(jpeg) > 100
