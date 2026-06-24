"""Upload validation. Uses libmagic for actual MIME sniffing — never trust
the client-reported content type."""

import magic

ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "png": ["image/png"],
    "jpg": ["image/jpeg"],
    "jpeg": ["image/jpeg"],
    # .xlsx is an OOXML zip container. libmagic reports it as the office-openxml
    # type on newer builds, but falls back to a generic zip/octet-stream on
    # others -- accept all three for the .xlsx extension. (The extension is still
    # required, and the parser (parse_prepared_xlsx) is the real structural gate:
    # a renamed .pdf/.zip without a valid workbook returns a parse error.)
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
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
