"""Upload validation. Uses libmagic for actual MIME sniffing — never trust
the client-reported content type."""

import magic

ALLOWED_MIME_TYPES = {
    "pdf": ["application/pdf"],
    "png": ["image/png"],
    "jpg": ["image/jpeg"],
    "jpeg": ["image/jpeg"],
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
