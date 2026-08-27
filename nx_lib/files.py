"""Upload validation. Uses libmagic for actual MIME sniffing — never trust
the client-reported content type."""

import magic

ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "png": ["image/png"],
    "jpg": ["image/jpeg"],
    "jpeg": ["image/jpeg"],
    # Organization logos (#98 phase 4). libmagic reports image/svg+xml when the
    # document opens with an XML declaration and the bare image/svg when it
    # doesn't -- both are the same thing. SVG is script-capable, so every
    # consumer must serve it sandboxed: nx_lib/views/core.py::branding_logo
    # sends Content-Security-Policy: sandbox + X-Content-Type-Options: nosniff.
    "svg": ["image/svg+xml", "image/svg"],
    # .xlsx is an OOXML zip container. libmagic reports it as the office-openxml
    # type on newer builds and a generic application/zip on older ones -- accept
    # both. application/octet-stream was dropped (#193): it is libmagic's
    # any-binary fallback, so allowing it collapsed the sniff to a bare
    # extension check. (The extension is still required, and the parser
    # (parse_prepared_xlsx) is the real structural gate: a renamed .pdf/.zip
    # without a valid workbook returns a parse error.)
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    ],
}


def is_file_allowed(filename, file_stream):
    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_MIME_TYPES:
        return False
    header = file_stream.read(2048)
    file_stream.seek(0)
    mime = magic.from_buffer(header, mime=True)
    return mime in ALLOWED_MIME_TYPES[ext]
